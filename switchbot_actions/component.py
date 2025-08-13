import logging
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from .config import BaseConfigModel

SettingsType = TypeVar("SettingsType", bound=BaseConfigModel)


class ComponentError(Exception):
    """Custom exception for component-related errors."""

    pass


class BaseComponent(ABC, Generic[SettingsType]):
    """Abstract base class for all components in the system."""

    def __init__(self, settings: SettingsType):
        """
        Initializes the component.

        Args:
            settings: The settings object for this component.
        """
        self.settings: SettingsType = settings
        self._running: bool = False
        self.logger = logging.getLogger(self.__class__.__module__)
        self._component_name = self.__class__.__name__

    @property
    def is_running(self) -> bool:
        """Returns True if the component is currently running."""
        return self._running

    @property
    def is_enabled(self) -> bool:
        """
        Determines if the component should be enabled based on its settings.
        This method calls the abstract `_is_enabled` method.
        """
        return self._is_enabled()

    async def start(self) -> None:
        """
        Starts the component if it is enabled and not already running.
        This method serves as a template method, calling the abstract `_start`.
        """
        if not self.is_enabled:
            self.logger.info(f"{self._component_name} is disabled, skipping start.")
            return

        if self._running:
            self.logger.warning(f"{self._component_name} is already running.")
            return

        self.logger.info(f"Starting {self._component_name}...")
        try:
            await self._start()
            self._running = True
            self.logger.info(f"{self._component_name} started successfully.")
        except Exception as e:
            self.logger.error(
                f"Failed to start {self._component_name}: {e}", exc_info=True
            )
            raise ComponentError(f"Failed to start {self._component_name}") from e

    async def stop(self) -> None:
        """
        Stops the component if it is currently running.
        This method serves as a template method, calling the abstract `_stop`.
        """
        if not self._running:
            self.logger.debug(f"{self._component_name} is not running.")
            return

        self.logger.info(f"Stopping {self._component_name}...")
        try:
            await self._stop()
            self._running = False
            self.logger.info(f"{self._component_name} stopped successfully.")
        except Exception as e:
            self.logger.error(
                f"Failed to stop {self._component_name}: {e}", exc_info=True
            )
            raise ComponentError(f"Failed to stop {self._component_name}") from e

    async def apply_new_settings(self, new_settings: SettingsType) -> None:
        """
        Applies new settings to the component, restarting it if necessary.
        This is the template method for configuration reloading.
        """
        if self.settings == new_settings:
            self.logger.debug(
                f"No settings changed for '{self._component_name}', skipping apply."
            )
            return

        # A restart is required if the component's enabled status changes,
        # or if the subclass determines a critical setting has changed.
        restart_needed = self._is_enabled() != self._is_enabled(
            new_settings
        ) or self._require_restart(new_settings)

        if restart_needed:
            self.logger.info(
                f"Applying settings for '{self._component_name}' requires a restart."
            )
            if self.is_running:
                await self.stop()

            self.settings = new_settings

            if self.is_enabled:  # Check against the new settings
                await self.start()
        elif self.is_running:
            # If running and no restart is needed, it's a live update.
            self.logger.info(
                f"Applying live update for component '{self._component_name}'."
            )
            await self._apply_live_update(new_settings)
            self.settings = new_settings
        else:
            # If not running and no restart is needed, just update the settings.
            self.settings = new_settings

    @abstractmethod
    def _is_enabled(self, settings: Optional[SettingsType] = None) -> bool:
        """
        Abstract method to determine if the component is enabled.
        If settings are provided, it checks based on them without changing state.
        """
        raise NotImplementedError

    @abstractmethod
    async def _start(self) -> None:
        """
        Abstract method for the component's startup logic.
        """
        raise NotImplementedError

    @abstractmethod
    async def _stop(self) -> None:
        """
        Abstract method for the component's shutdown logic.
        """
        raise NotImplementedError

    @abstractmethod
    def _require_restart(self, new_settings: SettingsType) -> bool:
        """
        Abstract method for subclasses to declare if a setting change
        requires a full component restart.
        """
        raise NotImplementedError

    @abstractmethod
    async def _apply_live_update(self, new_settings: SettingsType) -> None:
        """
        Abstract method for subclasses to apply settings changes that
        do not require a full restart.
        """
        raise NotImplementedError
