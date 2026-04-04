
# This is the entry point for the hevelius-runner code.
#
# It integrates all components:
# 1. Config Manager
# 2. API Client
# 3. Task Manager
# 4. File Monitor
# 5. Script Executor
# 6. NINA Controller
#
# It provides a complete workflow:
# 1. Startup script execution
# 2. Night time detection
# 3. Task planning and execution
# 4. FITS file monitoring
# 5. Status updates
# 6. Clean shutdown
#
# It includes proper error handling and logging throughout
#
# It implements the main control loop that:
# 1. Checks for night time
# 2. Processes observation plans
# 3. Monitors for new files
# 4. Handles status updates

import argparse
import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Optional

import yaml

from config_manager import ConfigManager
from api_client import APIClient, resolve_scope_id_from_identifier
from task_manager import TaskManager
from file_monitor import FileMonitor, FileMonitorThread
from script_executor import ScriptExecutor
from nina_controller import NINAController
from version import get_version
from cmd_repo import cmd_repo

class ObservatoryAutomation:
    def __init__(self, config: ConfigManager):
        """Initialize the observatory automation system."""
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.config = config
        self.api_client = APIClient(self.config.get_api_config())
        self.task_manager = TaskManager(self.config.get_paths_config())
        self.file_monitor = FileMonitor(self.config.get_paths_config())
        self.script_executor = ScriptExecutor(self.config.get_scripts_config())
        self.nina_controller = NINAController(self.config.get_nina_config())

        self.current_sequence_path = None
        self.observatory_id = "default"  # Should be configured or determined

    def setup_logging(self):
        """Configure logging for the application."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Full logging: format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(
                    log_dir / 'observatory.log',
                    maxBytes=1024*1024,
                    backupCount=5
                ),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def run(self):
        """Main execution loop of the automation system."""
        try:
            self.logger.info(f"Starting havelius-runner {get_version()}")

            # Execute startup script
            self.script_executor.execute_script('startup')

            # Ensure the API is reachable
            self.api_client.connect()

            # Start file monitoring
            monitor_thread = FileMonitorThread(self.file_monitor)
            self.file_monitor.start(self.handle_new_fits_file)
            monitor_thread.start()

            while True:
                try:
                    current_date = datetime.now().date()

                    # Check if it's night time and execute night start script
                    if self.is_night_time():
                        self.script_executor.execute_script('night_start')
                        self.process_night_plan(current_date)

                    # Wait before next check
                    time.sleep(60)  # Check every minute

                except KeyboardInterrupt:
                    self.logger.info("Received shutdown signal")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {str(e)}", exc_info=True)
                    time.sleep(300)  # Wait 5 minutes before retry

        finally:
            self.cleanup()

    def process_night_plan(self, date: datetime.date):
        """
        Process the observation plan for a night.

        Args:
            date: Date to process
        """
        try:
            # Get night plan from API
            tasks = self.api_client.get_night_plan(date.strftime("%Y-%m-%d"))
            if not tasks:
                self.logger.info("No tasks planned for tonight")
                return

            # Filter out completed tasks
            pending_tasks = [
                task for task in tasks
                if self.api_client.check_task_status(task['task_id']) != 'completed'
            ]

            if not pending_tasks:
                self.logger.info("All tasks for tonight are completed")
                return

            # Prepare sequence file
            self.current_sequence_path = self.task_manager.prepare_sequence_file(
                pending_tasks,
                self.observatory_id,
                date.strftime("%Y-%m-%d")
            )

            # Start NINA with the sequence
            if self.nina_controller.start_sequence(
                self.current_sequence_path,
                self.handle_nina_status
            ):
                self.logger.info(f"Started NINA with sequence: {self.current_sequence_path}")
            else:
                self.logger.error("Failed to start NINA")

        except Exception as e:
            self.logger.error(f"Error processing night plan: {str(e)}", exc_info=True)

    def handle_new_fits_file(self, file_path: str):
        """
        Handle newly detected FITS files.

        Args:
            file_path: Path to the new FITS file
        """
        try:
            # Extract task ID from file name or metadata
            task_id = self.extract_task_id_from_fits(file_path)
            if task_id:
                # Update task status
                self.api_client.update_task_status(
                    task_id,
                    "completed",
                    [file_path]
                )

                # Execute post-task script
                self.script_executor.execute_script('post_task', {
                    'task_id': task_id,
                    'fits_file': file_path
                })

        except Exception as e:
            self.logger.error(f"Error handling FITS file: {str(e)}")

    def handle_nina_status(self, status: str):
        """
        Handle status updates from NINA.

        Args:
            status: Status message from NINA
        """
        self.logger.info(f"NINA status: {status}")
        # Add specific status handling as needed

    def is_night_time(self) -> bool:
        """
        Check if it's currently night time for observations.

        Returns:
            bool: True if it's night time
        """
        # This is a simplified check - should be replaced with proper
        # astronomical twilight calculations for your location
        current_hour = datetime.now().hour
        return 18 <= current_hour or current_hour <= 6

    def extract_task_id_from_fits(self, file_path: str) -> str:
        """
        Extract task ID from FITS file name or metadata.

        Args:
            file_path: Path to the FITS file

        Returns:
            str: Task ID
        """
        # This is a placeholder - implement actual FITS header reading
        # or filename parsing based on your naming convention
        return Path(file_path).stem.split('_')[0]

    def cleanup(self):
        """Clean up resources before shutdown."""
        self.logger.info("Shutting down Observatory Automation")

        # Stop NINA if running
        if self.nina_controller.is_running():
            self.nina_controller.stop()

        # Stop file monitor
        self.file_monitor.stop()

        # Execute night end script
        self.script_executor.execute_script('night_end')

        # Stop script executor
        self.script_executor.stop_all()

        self.logger.info("Shutdown complete")


def _require_loaded_config(cm: ConfigManager) -> int:
    if cm.loaded:
        return 0
    print("Cannot continue without a valid configuration file.", file=sys.stderr)
    return 1


def cmd_config(cm: ConfigManager) -> int:
    if not cm.loaded:
        return 1
    print(f"# hevelius-runner configuration file: {cm.config_path.resolve()}")
    redacted = cm.redacted_copy()
    print(yaml.dump(redacted, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip())
    return 0


def cmd_check(cm: ConfigManager) -> int:
    code = _require_loaded_config(cm)
    if code != 0:
        return code

    api_cfg = cm.get_api_config()
    required_api = ("base_url", "timeout", "username", "password")
    missing = [k for k in required_api if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(
            f"API configuration is incomplete (missing: {', '.join(missing)}).",
            file=sys.stderr,
        )
        return 1

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
    try:
        version = client.get_version()
        print(f"API reachable at {api_cfg['base_url'].rstrip('/')}/ - backend version: {version}")
    except Exception as e:
        print(f"API check failed (version endpoint): {e}", file=sys.stderr)
        return 1

    try:
        login = client.login()
        if not login.status or not login.token:
            print(f"Login failed: {login.msg or 'no JWT token in response'}", file=sys.stderr)
            return 1
        print(f"Authenticated as {api_cfg['username']!r} (user id {login.user_id}).")
    except Exception as e:
        print(f"API check failed (login): {e}", file=sys.stderr)
        return 1

    try:
        scopes = client.list_telescopes()
        print(f"Telescopes available: {len(scopes)}")
        sid = api_cfg.get("scope_id")
        if sid is not None and str(sid).strip() != "":
            want = int(sid)
            ids = {int(t.get("scope_id")) for t in scopes if t.get("scope_id") is not None}
            if want not in ids:
                print(
                    f"Configured api.scope_id={want} is not in the telescope list from the API.",
                    file=sys.stderr,
                )
                return 1
            names = [t.get("name") for t in scopes if int(t.get("scope_id", -1)) == want]
            label = names[0] if names else "?"
            print(f"Configured scope_id {want} OK ({label!r}).")
        else:
            print(
                "Note: api.scope_id is not set; use `telescope list` and `telescope set`.",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"API check failed (telescope list): {e}", file=sys.stderr)
        return 1

    nina_cfg = cm.get_nina_config()
    exe = nina_cfg.get("executable_path", "")
    nina_path = Path(str(exe)) if exe else None
    if not nina_path or not nina_path.is_file():
        print(
            f"NINA executable not found or not configured: {exe!r}",
            file=sys.stderr,
        )
        return 1
    print(f"NINA executable found: {nina_path}")

    print("Configuration and connectivity check passed.")
    return 0


def cmd_run(cm: ConfigManager) -> int:
    code = _require_loaded_config(cm)
    if code != 0:
        return code
    api = cm.get_api_config()
    sid = api.get("scope_id")
    if sid is None or str(sid).strip() == "":
        print(
            "api.scope_id is not set. Run: hevelius-runner telescope list\n"
            "Then: hevelius-runner telescope set <id_or_name>",
            file=sys.stderr,
        )
        return 1
    app = ObservatoryAutomation(cm)
    app.run()
    return 0


def cmd_version(args: argparse.Namespace, cm: ConfigManager) -> int:
    print(f"hevelius-runner {get_version()}")
    if not getattr(args, "backend", False):
        return 0
    if not cm.loaded:
        print(
            "Cannot query backend version: configuration file is missing or invalid.",
            file=sys.stderr,
        )
        return 1
    api = cm.get_api_config()
    if not str(api.get("base_url", "")).strip():
        print("api.base_url is missing; cannot query backend version.", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
    merged = {
        **api,
        "username": api.get("username") or "_",
        "password": api.get("password") or "_",
        "timeout": int(api.get("timeout", 30)),
    }
    client = APIClient(merged)
    try:
        ver = client.get_version()
        print(f"Hevelius API version: {ver} ({api['base_url']})")
    except Exception as e:
        print(f"Could not reach API version endpoint: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_telescope_list(cm: ConfigManager) -> int:
    code = _require_loaded_config(cm)
    if code != 0:
        return code
    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
    try:
        client.get_version()
        client.login()
        scopes = client.list_telescopes()
    except Exception as e:
        print(f"Failed to list telescopes: {e}", file=sys.stderr)
        return 1
    if not scopes:
        print("No telescopes returned by the API.")
        return 0
    for t in scopes:
        sid = t.get("scope_id")
        name = t.get("name") or ""
        print(f"scope_id={sid}\t{name}")
    return 0


def cmd_telescope_set(cm: ConfigManager, identifier: str) -> int:
    code = _require_loaded_config(cm)
    if code != 0:
        return code
    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
    try:
        client.get_version()
        client.login()
        scope_id, matched_name = resolve_scope_id_from_identifier(client, identifier)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Failed to resolve telescope: {e}", file=sys.stderr)
        return 1
    try:
        cm.write_api_scope_id(scope_id)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    extra = f" ({matched_name!r})" if matched_name else ""
    print(f"Wrote api.scope_id = {scope_id}{extra} to {cm.config_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hevelius observatory runner - NINA integration and API client.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config/config.yaml",
        help="Path to YAML configuration; place this option before COMMAND (default: config/config.yaml)",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("run", help="Start the automation loop.")
    sub.add_parser("config", help="Print effective configuration (password redacted).")
    sub.add_parser(
        "check",
        help="Verify YAML config, API reachability, JWT login, telescopes, and NINA executable path.",
    )
    version_parser = sub.add_parser("version", help="Print hevelius-runner version.")
    version_parser.add_argument(
        "--backend",
        action="store_true",
        help="Also query the Hevelius API /version endpoint (uses api.base_url from config).",
    )
    tel = sub.add_parser("telescope", help="List telescopes or set api.scope_id in the config file.")
    tel_sub = tel.add_subparsers(dest="telescope_cmd", metavar="SUBCOMMAND", required=True)
    tel_sub.add_parser(
        "list",
        help="Print scope_id and name for each telescope (JWT required).",
    )
    p_set = tel_sub.add_parser(
        "set",
        help="Resolve id or name and write api.scope_id to config.yaml.",
    )
    p_set.add_argument(
        "identifier",
        help="Numeric scope_id or exact telescope name (see telescope list).",
    )

    repo_parser = sub.add_parser('repo', help="Manages files repository on local storage.")
    repo_parser.add_argument('-f', "--file", help="Reads a single FITS file", type=str)
    repo_parser.add_argument("-l", "--list", help="Reads a list of FITS files (one filename per line)", type=str)
    repo_parser.add_argument("-d", "--dir",   help="Reads all FITS files recursively", type=str)
    repo_parser.add_argument("-s", "--show-header", help="Displays all entries in FITS header", action='store_true')
    repo_parser.add_argument("-t", "--dry-run", help="Don't do the actual DB upsert", action='store_true')
    repo_parser.add_argument("--sanity-db", help="Goes through the list of tasks in a database and checks if all files are present", action='store_true')
    repo_parser.add_argument("--sanity-files", help="Goes through the list of files and check if related tasks are present", action='store_true')
    repo_parser.add_argument("--min-task-id", help="Minimum task ID to check (for sanity-db)", type=int)
    repo_parser.add_argument("--max-task-id", help="Maximum task ID to check (for sanity-db)", type=int)
    repo_parser.add_argument("--delete-invalid", help="Delete invalid tasks (no filename or missing file) when using sanity-db", action='store_true')

    return parser

def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command

    if command is None:
        parser.print_help()
        return 0

    cm = ConfigManager(args.config)

    if command == "run":
        return cmd_run(cm)
    if command == "config":
        return cmd_config(cm)
    if command == "check":
        return cmd_check(cm)
    if command == "version":
        return cmd_version(args, cm)
    if command == "telescope":
        if args.telescope_cmd == "list":
            return cmd_telescope_list(cm)
        if args.telescope_cmd == "set":
            return cmd_telescope_set(cm, args.identifier)
    if args.command == "repo":
        return cmd_repo(cm, args)  # see cmd_repo.py

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
