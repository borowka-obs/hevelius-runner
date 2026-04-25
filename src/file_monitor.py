import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Set, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
import threading

class FITSHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str], None], file_extension: str = ".fits"):
        """
        Initialize the FITS file handler.
        
        Args:
            callback: Function to call when new FITS file is detected
            file_extension: File extension to monitor (default: .fits)
        """
        self.callback = callback
        self.file_extension = file_extension.lower()
        self.logger = logging.getLogger(__name__)
        self._processing_lock = threading.Lock()
        self._processed_files: Set[str] = set()

    def on_created(self, event: FileCreatedEvent):
        """
        Handle file creation events.
        
        Args:
            event: File system event
        """
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() == self.file_extension:
                self._handle_new_file(str(file_path))

    def _handle_new_file(self, file_path: str):
        """
        Process new FITS file.
        
        Args:
            file_path: Path to the new FITS file
        """
        with self._processing_lock:
            if file_path in self._processed_files:
                return
            
            # Wait for file to be completely written
            self._wait_for_file_ready(file_path)
            
            try:
                self.logger.info(f"Processing new FITS file: {file_path}")
                self.callback(file_path)
                self._processed_files.add(file_path)
            except Exception as e:
                self.logger.error(f"Error processing file {file_path}: {str(e)}")

    def _wait_for_file_ready(self, file_path: str, timeout: int = 30):
        """
        Wait for file to be completely written.
        
        Args:
            file_path: Path to the file
            timeout: Maximum time to wait in seconds
        """
        start_time = time.time()
        last_size = -1
        
        while time.time() - start_time < timeout:
            try:
                current_size = Path(file_path).stat().st_size
                if current_size == last_size and current_size > 0:
                    return
                last_size = current_size
                time.sleep(1)
            except FileNotFoundError:
                self.logger.warning(f"File disappeared while waiting: {file_path}")
                return
            
        self.logger.warning(f"Timeout waiting for file to be ready: {file_path}")

class FileMonitor:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the file monitor.
        
        Args:
            config: Dictionary containing monitoring configuration
        """
        self.monitor_volumes = self._parse_monitor_volumes(config)
        self.logger = logging.getLogger(__name__)
        self.observer = Observer()
        self._stop_event = threading.Event()
        self._callback = None

    def _parse_monitor_volumes(self, config: Dict[str, Any]) -> List[Tuple[Path, str]]:
        volumes_raw = config.get("volumes")
        parsed: List[Tuple[Path, str]] = []

        if isinstance(volumes_raw, list):
            for idx, volume in enumerate(volumes_raw):
                if isinstance(volume, str):
                    nickname = f"volume-{idx + 1}"
                    parsed.append((Path(volume), nickname))
                    continue

                if isinstance(volume, dict):
                    raw_path = volume.get("path")
                    if not raw_path:
                        raise ValueError(f"paths.volumes[{idx}] is missing required key 'path'")
                    nickname = str(volume.get("nickname") or f"volume-{idx + 1}")
                    parsed.append((Path(str(raw_path)), nickname))
                    continue

                raise ValueError(
                    f"paths.volumes[{idx}] must be a string or mapping with 'path' and optional 'nickname'"
                )

        if parsed:
            return parsed

        # Backward compatibility with old config key.
        fallback_dir = config.get("fits_monitor_dir")
        if fallback_dir:
            return [(Path(str(fallback_dir)), "default")]

        raise ValueError(
            "No FITS monitor directories configured. Set paths.volumes in your config."
        )

    def start(self, callback: Callable[[str], None]):
        """
        Start monitoring for new FITS files.
        
        Args:
            callback: Function to call when new FITS file is detected
        """
        self._callback = callback
        
        # Set up and start observers for all configured volumes
        handler = FITSHandler(callback)
        for volume_path, nickname in self.monitor_volumes:
            volume_path.mkdir(parents=True, exist_ok=True)
            self.observer.schedule(handler, str(volume_path), recursive=False)
            self.logger.info(
                f"Starting file monitor in volume '{nickname}': {volume_path}"
            )

        self.observer.start()

    def stop(self):
        """Stop monitoring for new files."""
        self.logger.info("Stopping file monitor")
        self._stop_event.set()
        self.observer.stop()
        self.observer.join()

    def is_running(self) -> bool:
        """
        Check if the monitor is running.
        
        Returns:
            bool: True if monitor is running
        """
        return self.observer.is_alive()

    def process_existing_files(self):
        """Process any existing FITS files in all monitor volumes."""
        try:
            for volume_path, nickname in self.monitor_volumes:
                for file_path in volume_path.glob("*.fits"):
                    if self._callback and file_path.is_file():
                        self.logger.info(
                            f"Processing existing file from volume '{nickname}': {file_path}"
                        )
                        self._callback(str(file_path))
        except Exception as e:
            self.logger.error(f"Error processing existing files: {str(e)}")

class FileMonitorThread(threading.Thread):
    def __init__(self, file_monitor: FileMonitor):
        """
        Initialize the file monitor thread.
        
        Args:
            file_monitor: FileMonitor instance to run in thread
        """
        super().__init__()
        self.file_monitor = file_monitor
        self.daemon = True

    def run(self):
        """Run the file monitor in a separate thread."""
        try:
            while not self.file_monitor._stop_event.is_set():
                time.sleep(1)
        except Exception as e:
            self.file_monitor.logger.error(f"Error in monitor thread: {str(e)}")
        finally:
            self.file_monitor.stop() 