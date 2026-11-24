"""Kafka consumer of the scheduler.

It reads the instances from a topic, computes their rosters as /schedule does,
and sends the result to the topic given by the ReplyTopic header of each
request, with the same CorrelationId header.

Same design as the Kafka consumer of AI4WORK-Project/logistics-scheduler.
"""

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from confluent_kafka import Consumer, KafkaError, Message, Producer

import service

logger = logging.getLogger("healthcare-scheduler-kafka")

HEADER_CORRELATION_ID = "CorrelationId"
HEADER_REPLY_TOPIC = "ReplyTopic"
HEADER_TIME_LIMIT = "TimeLimit"
HEADER_STATUS = "Status"

GROUP_ID = "healthcare-scheduler"

DEFAULT_TIME_LIMIT = 120
MAX_TIME_LIMIT = 3600
# a consumer that does not poll for longer than this leaves its group and its
# messages are delivered again: it must cover the longest solve, which runs
# between two polls
MAX_POLL_INTERVAL_MS = (MAX_TIME_LIMIT + 300) * 1000


def parse_time_limit(value: str, name: str) -> int:
    """Return a time limit in seconds, between 1 and MAX_TIME_LIMIT.

    Raise ValueError if the value is not valid."""
    try:
        time_limit = int(value)
    except ValueError:
        time_limit = 0
    if not 0 < time_limit <= MAX_TIME_LIMIT:
        raise ValueError(
            f"{name} must be an integer between 1 and {MAX_TIME_LIMIT}, got '{value}'"
        )
    return time_limit


@dataclass
class KafkaConfig:
    bootstrap_server: str
    topic: str
    username: str | None = None
    password: str | None = None
    time_limit: int = DEFAULT_TIME_LIMIT

    @classmethod
    def from_env(cls) -> "KafkaConfig | None":
        """Read the configuration from the environment variables.

        Return None if KAFKA_BOOTSTRAP_SERVER is not set, and raise ValueError
        if the configuration is not valid."""
        bootstrap_server = os.getenv("KAFKA_BOOTSTRAP_SERVER")
        if not bootstrap_server:
            return None
        topic = os.getenv("KAFKA_TOPIC_HEALTHCARE_INSTANCE")
        if not topic:
            raise ValueError(
                "KAFKA_TOPIC_HEALTHCARE_INSTANCE is required with KAFKA_BOOTSTRAP_SERVER"
            )
        time_limit = parse_time_limit(
            os.getenv("KAFKA_TIME_LIMIT", str(DEFAULT_TIME_LIMIT)), "KAFKA_TIME_LIMIT"
        )
        return cls(
            bootstrap_server=bootstrap_server,
            topic=topic,
            username=os.getenv("KAFKA_USERNAME"),
            password=os.getenv("KAFKA_PASSWORD"),
            time_limit=time_limit,
        )

    def client_config(self) -> dict[str, Any]:
        """Configuration common to the consumer and the producer."""
        config: dict[str, Any] = {"bootstrap.servers": self.bootstrap_server}
        if self.username is not None and self.password is not None:
            config.update(
                {
                    "security.protocol": "SASL_PLAINTEXT",
                    "sasl.mechanism": "PLAIN",
                    "sasl.username": self.username,
                    "sasl.password": self.password,
                }
            )
        return config


def message_headers(msg: Message) -> dict[str, str]:
    """Return the headers of a message decoded as UTF-8: the last value wins."""
    headers = {}
    for key, value in msg.headers() or []:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if value is not None:
            headers[key] = value
    return headers


class KafkaWorker:
    """Consume the requests until stop() is called.

    on_schedule is called with the problem and the solution of each solved
    request."""

    def __init__(
        self,
        config: KafkaConfig,
        on_schedule: Callable[..., None] | None = None,
    ):
        self.config = config
        self.on_schedule = on_schedule
        self._stopping = threading.Event()

    def stop(self):
        """Ask the worker to stop: it closes the consumer after the request in
        progress, if any."""
        self._stopping.set()

    def run(self):
        """Consume the requests until stop() is called.

        The consumer is used and closed only by the thread running this method,
        since it is not safe to close it while another thread polls it."""
        logger.info(f"Kafka bootstrap server: {self.config.bootstrap_server}")
        consumer = Consumer(
            {
                **self.config.client_config(),
                "group.id": GROUP_ID,
                "allow.auto.create.topics": "true",
                "auto.offset.reset": "earliest",
                # commit a request only once its reply has been sent, so that a
                # request is not lost if the scheduler stops while solving it
                "enable.auto.commit": "false",
                "max.poll.interval.ms": MAX_POLL_INTERVAL_MS,
            }
        )
        producer = Producer({**self.config.client_config(), "acks": "all"})
        try:
            # asking for the metadata of the topic creates it, if the broker
            # allows it
            topic = self.config.topic
            metadata = consumer.list_topics(topic, timeout=10)
            found = metadata.topics is not None and topic in metadata.topics
            logger.info(f"Topic {topic} {'found' if found else 'not found'}")

            logger.info(f"Subscribing to topic {topic}")
            consumer.subscribe([topic])
            self._consume(consumer, producer)
        finally:
            logger.info("Closing the Kafka consumer")
            consumer.close()
            producer.flush(5)

    def _consume(self, consumer: Consumer, producer: Producer):
        waiting = True
        while not self._stopping.is_set():
            msg = consumer.poll(1.0)
            if msg is None:
                if waiting:
                    logger.info(f"Waiting... for requests on topic {self.config.topic}")
                    waiting = False
                continue

            error = msg.error()
            if error is not None:
                if error.code() in (
                    KafkaError.UNKNOWN_TOPIC_OR_PART,
                    KafkaError._UNKNOWN_TOPIC,
                    KafkaError._UNKNOWN_PARTITION,
                ):
                    logger.warning(f"Failed to poll topic {self.config.topic}: {error}")
                else:
                    logger.error(f"Failed to poll topic {self.config.topic}: {error}")
                continue

            try:
                self._handle(msg, producer)
            except Exception:
                logger.exception("Failed to handle a request")
            consumer.commit(message=msg, asynchronous=False)
            waiting = True

    def _handle(self, msg: Message, producer: Producer):
        headers = message_headers(msg)
        correlation_id = headers.get(HEADER_CORRELATION_ID)
        reply_topic = headers.get(HEADER_REPLY_TOPIC)
        if not correlation_id or not reply_topic:
            logger.error(
                f"Ignoring a request without the {HEADER_CORRELATION_ID} or "
                f"{HEADER_REPLY_TOPIC} header"
            )
            return

        logger.info(f"Received request {correlation_id}")
        result = self._schedule(msg.value(), headers)
        self._reply(producer, reply_topic, correlation_id, result)

        if result.schedule is not None and self.on_schedule:
            self.on_schedule(*result.schedule)

    def _schedule(
        self, value: bytes | None, headers: dict[str, str]
    ) -> service.ScheduleResult:
        time_limit_header = headers.get(HEADER_TIME_LIMIT)
        if time_limit_header is None:
            time_limit = self.config.time_limit
        else:
            try:
                time_limit = parse_time_limit(time_limit_header, HEADER_TIME_LIMIT)
            except ValueError as e:
                return service.validation_error(e)

        try:
            data = json.loads(value or b"")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return service.validation_error(ValueError(f"Invalid JSON: {e}"))

        return service.schedule(data, time_limit)

    def _reply(
        self,
        producer: Producer,
        reply_topic: str,
        correlation_id: str,
        result: service.ScheduleResult,
    ):
        def on_delivery(error, msg):
            if error:
                logger.error(f"Failed to send the reply to {correlation_id}: {error}")
            else:
                logger.info(
                    f"Sent the reply to {correlation_id} with status {result.status} "
                    f"to topic {msg.topic()}"
                )

        producer.produce(
            reply_topic,
            result.body,
            headers=[
                (HEADER_CORRELATION_ID, correlation_id.encode("utf-8")),
                (HEADER_STATUS, str(result.status).encode("utf-8")),
            ],
            on_delivery=on_delivery,
        )
        if producer.flush(10) > 0:
            logger.error(f"The reply to {correlation_id} has not been sent in time")
