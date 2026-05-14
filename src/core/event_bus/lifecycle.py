from __future__ import annotations

import random
from dataclasses import dataclass

from src.models.event import Event, EventPhase
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LifecycleAdvancement:
    event_id: str
    old_phase: str
    new_phase: str
    prompt_to_inject: str | None  # LLM prompt to inject, if any
    silent_effects: dict | None   # Backend state changes, if any


class LifecycleManager:
    """
    Manages the three-phase lifecycle of events:
    Foreshadowing → Transition → Active → Expired
    """

    def __init__(self, foreshadow_probability: float = 0.3):
        self.foreshadow_probability = foreshadow_probability

    async def advance(
        self, event: Event, game_date: str
    ) -> LifecycleAdvancement | None:
        """
        Advance an event through its lifecycle based on date proximity.
        Called during settlement (time slot / day transitions).
        Returns lifecycle advancement info if phase changed.
        """
        old_phase = event.phase.value

        if event.phase == EventPhase.PENDING:
            # Check if we should enter foreshadowing
            if event.foreshadow_start_date and game_date >= event.foreshadow_start_date:
                if game_date >= (event.active_start_date or event.required_date or game_date):
                    # Past foreshadowing — jump to transition or active
                    if event.transition_date and game_date >= event.transition_date:
                        event.phase = EventPhase.ACTIVE
                        event.is_active = True
                        return LifecycleAdvancement(
                            event_id=event.id,
                            old_phase=old_phase,
                            new_phase=EventPhase.ACTIVE.value,
                            prompt_to_inject=event.active_prompt,
                            silent_effects=None,
                        )
                else:
                    event.phase = EventPhase.FORESHADOWING
                    # Foreshadowing only injects with probability
                    prompt = None
                    if random.random() < self.foreshadow_probability:
                        prompt = event.foreshadow_prompt
                    return LifecycleAdvancement(
                        event_id=event.id,
                        old_phase=old_phase,
                        new_phase=EventPhase.FORESHADOWING.value,
                        prompt_to_inject=prompt,
                        silent_effects=None,
                    )

        elif event.phase == EventPhase.FORESHADOWING:
            # Check transition date
            if event.transition_date and game_date >= event.transition_date:
                event.phase = EventPhase.TRANSITION
                return LifecycleAdvancement(
                    event_id=event.id,
                    old_phase=old_phase,
                    new_phase=EventPhase.TRANSITION.value,
                    prompt_to_inject=event.ai_setup_prompt,
                    silent_effects=None,
                )

        elif event.phase == EventPhase.TRANSITION:
            # Check active start date
            if event.active_start_date and game_date >= event.active_start_date:
                event.phase = EventPhase.ACTIVE
                event.is_active = True
                return LifecycleAdvancement(
                    event_id=event.id,
                    old_phase=old_phase,
                    new_phase=EventPhase.ACTIVE.value,
                    prompt_to_inject=event.active_prompt,
                    silent_effects=event.silent_effects,
                )

        elif event.phase == EventPhase.ACTIVE:
            # Check expiry
            if event.active_end_date and game_date > event.active_end_date:
                event.phase = EventPhase.EXPIRED
                event.is_active = False
                return LifecycleAdvancement(
                    event_id=event.id,
                    old_phase=old_phase,
                    new_phase=EventPhase.EXPIRED.value,
                    prompt_to_inject=None,
                    silent_effects=None,
                )

        return None
