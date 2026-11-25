import json
import logging
import pathlib
import threading
import time
import uuid

import pytest
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from testcontainers.community.kafka import KafkaContainer

import kafka_worker
import server
from kafka_worker import KafkaConfig, KafkaWorker

logger = logging.getLogger("test_kafka_worker")

INSTANCES_PATH = pathlib.Path(__file__).parent.resolve() / "instances"

REQUEST_TOPIC = "healthcare-instance"
REPLY_TOPIC = "healthcare-solution"


@pytest.fixture(scope="session")
def kafka_config(request) -> KafkaConfig:
    """Kafka broker with SASL PLAIN authentication, as in Pilot-Logistics."""
    with (
        KafkaContainer(
            image="confluentinc/cp-kafka:8.3.2",
            listener_name="SASL_PLAINTEXT",
            security_protocol="SASL_PLAINTEXT",
        )
        .with_env("KAFKA_SASL_ENABLED_MECHANISMS", "PLAIN")
        .with_env("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "true")
        .with_env(
            "KAFKA_OPTS",
            "-Djava.security.auth.login.config=/etc/kafka/kafka_server_jaas.conf",
        )
        .with_volume_mapping(
            str(request.config.rootpath / "tests/config/kafka_server_jaas.conf"),
            "/etc/kafka/kafka_server_jaas.conf",
        )
        .with_kraft() as kafka
    ):
        bootstrap_server = kafka.get_bootstrap_server()
        logger.info(f"bootstrap_server: {bootstrap_server}")
        yield KafkaConfig(
            bootstrap_server=bootstrap_server,
            topic=REQUEST_TOPIC,
            username="user",
            password="password",
            time_limit=30,
        )


class KafkaClient:
    """Sends the requests and waits for their replies."""

    def __init__(self, config: KafkaConfig):
        self.producer = Producer({**config.client_config(), "acks": "all"})
        self.consumer = Consumer(
            {
                **config.client_config(),
                "group.id": f"test-client-{uuid.uuid4()}",
                "allow.auto.create.topics": "true",
                "auto.offset.reset": "earliest",
            }
        )
        self.consumer.list_topics(REPLY_TOPIC, timeout=10)
        self.consumer.subscribe([REPLY_TOPIC])
        self.replies: dict[str, tuple[dict, dict]] = {}

    def send(
        self,
        value: str | bytes,
        topic: str = REQUEST_TOPIC,
        correlation_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        correlation_id = correlation_id or str(uuid.uuid4())
        if headers is None:
            headers = {"CorrelationId": correlation_id, "ReplyTopic": REPLY_TOPIC}
        self.producer.produce(
            topic, value, headers=[(k, v.encode()) for k, v in headers.items()]
        )
        assert self.producer.flush(10) == 0, "The request has not been sent"
        return correlation_id

    def poll(self, timeout: float):
        """Collect the replies received within the timeout."""
        msg = self.consumer.poll(timeout)
        if msg is not None and msg.error() is None:
            headers = kafka_worker.message_headers(msg)
            self.replies[headers["CorrelationId"]] = (json.loads(msg.value()), headers)

    def reply(self, correlation_id: str, timeout: float = 90) -> tuple[int, dict]:
        """Wait for the reply to a request and return its status and body."""
        deadline = time.monotonic() + timeout
        while correlation_id not in self.replies:
            assert time.monotonic() < deadline, "No reply received"
            self.poll(1.0)
        body, headers = self.replies[correlation_id]
        return int(headers["Status"]), body

    def schedule(self, instance: dict, **kwargs) -> tuple[int, dict]:
        return self.reply(self.send(json.dumps(instance), **kwargs))

    def close(self):
        self.consumer.close()
        self.producer.flush(5)


def start_worker(config: KafkaConfig) -> tuple[KafkaWorker, threading.Thread]:
    worker = KafkaWorker(config)
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    return worker, thread


@pytest.fixture(scope="module")
def worker(kafka_config: KafkaConfig):
    worker, thread = start_worker(kafka_config)
    yield worker
    worker.stop()
    thread.join(10)


@pytest.fixture(scope="module")
def client(kafka_config: KafkaConfig, worker: KafkaWorker):
    client = KafkaClient(kafka_config)
    yield client
    client.close()


def instance(name: str = "instance0.json") -> dict:
    with open(INSTANCES_PATH / name) as f:
        return json.load(f)


def test_valid_instance(client: KafkaClient):
    status, body = client.schedule(instance())
    assert status == 200
    assert len(body["shift_schedule"]) > 0
    assert "underallocations" in body


def test_correlation_id(client: KafkaClient):
    correlation_id = client.send(json.dumps(instance()))
    client.reply(correlation_id)
    _, headers = client.replies[correlation_id]
    assert headers["CorrelationId"] == correlation_id


def test_time_limit_header(client: KafkaClient):
    correlation_id = str(uuid.uuid4())
    headers = {
        "CorrelationId": correlation_id,
        "ReplyTopic": REPLY_TOPIC,
        "TimeLimit": "10",
    }
    client.send(json.dumps(instance()), correlation_id=correlation_id, headers=headers)
    status, _ = client.reply(correlation_id)
    assert status == 200


@pytest.mark.parametrize("time_limit", ["abc", "1.5", "0", "3601"])
def test_invalid_time_limit_header(client: KafkaClient, time_limit: str):
    correlation_id = str(uuid.uuid4())
    headers = {
        "CorrelationId": correlation_id,
        "ReplyTopic": REPLY_TOPIC,
        "TimeLimit": time_limit,
    }
    client.send(json.dumps(instance()), correlation_id=correlation_id, headers=headers)
    status, body = client.reply(correlation_id)
    assert status == 422
    assert body["message"] == "Validation error"
    assert body["detail"].startswith("TimeLimit must be an integer")


def test_malformed_json(client: KafkaClient):
    status, body = client.reply(client.send('{"horizon": 7,'))
    assert status == 422
    assert body["detail"].startswith("Invalid JSON")


def test_missing_field(client: KafkaClient):
    request = instance()
    del request["horizon"]
    status, body = client.schedule(request)
    assert status == 422
    assert body == {"message": "Validation error", "detail": "Missing field 'horizon'"}


def test_invalid_field_value(client: KafkaClient):
    request = instance()
    request["horizon"] = 0
    status, body = client.schedule(request)
    assert status == 422
    assert body["detail"] == "The horizon must be greater than 0"


def test_instance_not_solvable(client: KafkaClient):
    status, body = client.schedule(instance("instance_not_solvable.json"))
    assert status == 400
    assert body == {"message": "No solution has been found for the given problem"}


def test_missing_headers(client: KafkaClient):
    # a request without ReplyTopic cannot be answered: it is skipped, and the
    # following requests are still answered
    ignored = client.send(
        json.dumps(instance()), headers={"CorrelationId": "without-reply-topic"}
    )
    status, _ = client.schedule(instance())
    assert status == 200
    assert ignored not in client.replies


def test_requests_are_committed(kafka_config: KafkaConfig, client: KafkaClient):
    # a worker started after the others must not answer the requests they have
    # already answered: they are committed after their reply
    test_valid_instance(client)
    answered = len(client.replies)

    restarted, thread = start_worker(kafka_config)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            client.poll(1.0)
        assert len(client.replies) == answered
    finally:
        restarted.stop()
        thread.join(10)


def test_server_kafka_worker(kafka_config: KafkaConfig, monkeypatch):
    # the server shows the schedules computed for the Kafka requests and the
    # state of the consumer in /health
    topic = "healthcare-instance-server"
    config = KafkaConfig(**{**kafka_config.__dict__, "topic": topic})
    gantt = server.LastScheduleGantt(server.render_roster)
    monkeypatch.setattr(server, "last_schedule_gantt_html", gantt)
    monkeypatch.setattr(server, "kafka_consumer", None)
    monkeypatch.setattr(server, "kafka_thread", None)
    exits: list[int] = []
    monkeypatch.setattr(server, "exit_process", exits.append)
    http = server.app.test_client()

    worker = server.start_kafka_worker(config)
    kafka_client = KafkaClient(config)
    try:
        # "connecting" until the consumer has subscribed to the topic
        assert server.kafka_consumer.connected.wait(30)
        response = http.get("/health")
        assert response.status_code == 200
        assert response.json["kafka"] == "running"

        status, body = kafka_client.schedule(instance(), topic=topic)
        assert status == 200
        html = http.get("/last_schedule_gantt").get_data(as_text=True)
        for employee in body["shift_schedule"]:
            assert employee["employee_id"] in html
    finally:
        kafka_client.close()
        worker.stop()
        server.kafka_thread.join(10)

    response = http.get("/health")
    assert response.status_code == 503
    assert response.json == {
        "status": "unhealthy",
        "version": server.__version__,
        "kafka": "stopped",
    }
    assert exits == []


def test_processing_error(client: KafkaClient, monkeypatch):
    # an unexpected error still gets a reply, as /schedule does
    def fail(*args, **kwargs):
        raise RuntimeError("solver failure")

    monkeypatch.setattr(kafka_worker.service, "schedule", fail)
    status, body = client.schedule(instance())
    assert status == 500
    assert body == {"message": "solver failure"}


def unreachable_config(kafka_config: KafkaConfig) -> KafkaConfig:
    return KafkaConfig(**{**kafka_config.__dict__, "bootstrap_server": "localhost:1"})


def test_server_waits_for_broker(kafka_config: KafkaConfig, monkeypatch):
    # the consumer keeps trying to reach the broker, and /health reports it
    monkeypatch.setattr(kafka_worker, "RETRY_INTERVAL", 0.1)
    monkeypatch.setattr(server, "kafka_consumer", None)
    monkeypatch.setattr(server, "kafka_thread", None)
    exits: list[int] = []
    monkeypatch.setattr(server, "exit_process", exits.append)
    http = server.app.test_client()

    worker = server.start_kafka_worker(unreachable_config(kafka_config))
    try:
        time.sleep(1)
        assert server.kafka_thread.is_alive()
        response = http.get("/health")
        assert response.status_code == 503
        assert response.json["kafka"] == "connecting"
    finally:
        worker.stop()
        server.kafka_thread.join(15)
    assert not server.kafka_thread.is_alive()
    assert exits == []


def test_server_exits_when_consumer_fails(kafka_config: KafkaConfig, monkeypatch):
    # a consumer that stops on its own makes the process exit, so that the
    # container can be restarted
    def run(self):
        raise KafkaException(KafkaError(KafkaError._FATAL))

    monkeypatch.setattr(kafka_worker.KafkaWorker, "run", run)
    monkeypatch.setattr(server, "kafka_consumer", None)
    monkeypatch.setattr(server, "kafka_thread", None)
    exits: list[int] = []
    monkeypatch.setattr(server, "exit_process", exits.append)

    server.start_kafka_worker(kafka_config)
    server.kafka_thread.join(10)
    assert exits == [1]


class FailingCommitConsumer:
    def commit(self, **kwargs):
        raise KafkaException(KafkaError(KafkaError.REBALANCE_IN_PROGRESS))


def test_commit_error(kafka_config: KafkaConfig):
    # a commit that fails, e.g. during a rebalance, does not stop the consumer
    KafkaWorker(kafka_config)._commit(FailingCommitConsumer(), None)


class FakeProducer:
    """Reports the given delivery outcomes, one per message: None for a
    delivered message, an error code for a failed one, and "pending" for a
    message that is never delivered."""

    def __init__(self, outcomes: list):
        self.outcomes = outcomes
        self.produced = 0
        self.callbacks = []

    def produce(self, topic, value, headers, on_delivery):
        outcome = self.outcomes[self.produced]
        self.produced += 1
        if outcome != "pending":
            error = None if outcome is None else KafkaError(outcome)
            self.callbacks.append(lambda: on_delivery(error, None))

    def flush(self, timeout):
        while self.callbacks:
            self.callbacks.pop(0)()
        return 0


def send_reply(worker: KafkaWorker, producer: FakeProducer) -> bool:
    return worker._reply(
        producer, REPLY_TOPIC, "id", kafka_worker.service.internal_error(Exception())
    )


def test_reply_temporary_error(kafka_config: KafkaConfig, monkeypatch):
    # a reply that fails for a temporary error is sent again
    monkeypatch.setattr(kafka_worker, "RETRY_INTERVAL", 0)
    producer = FakeProducer([KafkaError._MSG_TIMED_OUT, KafkaError._TRANSPORT, None])
    assert send_reply(KafkaWorker(kafka_config), producer)
    assert producer.produced == 3


def test_reply_permanent_error(kafka_config: KafkaConfig):
    # a reply that cannot be delivered at all is given up
    producer = FakeProducer([KafkaError.TOPIC_AUTHORIZATION_FAILED])
    assert send_reply(KafkaWorker(kafka_config), producer)
    assert producer.produced == 1


def test_reply_not_sent_when_stopping(kafka_config: KafkaConfig):
    # a reply not delivered when the worker stops is reported, so that its
    # request is not committed
    worker = KafkaWorker(kafka_config)
    worker.stop()
    assert not send_reply(worker, FakeProducer(["pending"]))


def test_config_from_env(monkeypatch):
    for name in (
        "KAFKA_BOOTSTRAP_SERVER",
        "KAFKA_TOPIC_HEALTHCARE_INSTANCE",
        "KAFKA_USERNAME",
        "KAFKA_PASSWORD",
        "KAFKA_TIME_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert KafkaConfig.from_env() is None

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVER", "kafka:9092")
    with pytest.raises(ValueError, match="KAFKA_TOPIC_HEALTHCARE_INSTANCE"):
        KafkaConfig.from_env()

    monkeypatch.setenv("KAFKA_TOPIC_HEALTHCARE_INSTANCE", "healthcare-instance")
    config = KafkaConfig.from_env()
    assert config == KafkaConfig("kafka:9092", "healthcare-instance")
    assert config.time_limit == kafka_worker.DEFAULT_TIME_LIMIT
    assert "sasl.username" not in config.client_config()

    monkeypatch.setenv("KAFKA_USERNAME", "user")
    monkeypatch.setenv("KAFKA_PASSWORD", "password")
    monkeypatch.setenv("KAFKA_TIME_LIMIT", "300")
    config = KafkaConfig.from_env()
    assert config.time_limit == 300
    assert config.client_config()["sasl.username"] == "user"

    monkeypatch.setenv("KAFKA_TIME_LIMIT", "forever")
    with pytest.raises(ValueError, match="KAFKA_TIME_LIMIT"):
        KafkaConfig.from_env()
