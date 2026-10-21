"""The detection pipeline: quick check, reasoning check and claim check on one local model."""

from fisherman.pipeline.destinations import Destinations
from fisherman.pipeline.pipeline import Pipeline
from fisherman.pipeline.prompts import Prompts

__all__ = ["Destinations", "Pipeline", "Prompts"]
