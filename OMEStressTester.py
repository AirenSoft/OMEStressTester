import subprocess
import threading
import time
import http.server
import socketserver
import logging
import os
import signal
import json
import configparser

# -------------------------------
# Version Information
# -------------------------------
VERSION = "1.0.0"

# -------------------------------
# Load Configuration
# -------------------------------
config = configparser.ConfigParser()
config.read('config.ini')

LOG_FILE = "ome-stress-tester.log"
ALERT_CALLBACK_SERVER_PORT = config.getint(
    'Server', 'alert_callback_server_port')
FFMPEG_EXECUTION_INTERVAL = config.getint(
    'Stream', 'ffmpeg_execution_interval')
FFMPEG_COMMAND = config.get('Stream', 'ffmpeg_command')

MESSAGE_CODES = [
    "INTERNAL_QUEUE_CONGESTION",
    "EGRESS_STREAM_CREATION_FAILED_BY_OUTPUT_PROFILE",
    "EGRESS_STREAM_CREATION_FAILED_BY_DECODER",
    "EGRESS_STREAM_CREATION_FAILED_BY_ENCODER",
    "EGRESS_STREAM_CREATION_FAILED_BY_FILTER",
]

# -------------------------------
# Logger Configuration
# -------------------------------
# Create file handler with DEBUG level
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"))

# Create console handler with INFO level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(message)s"))

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all levels
    handlers=[
        file_handler,
        console_handler
    ]
)

# -------------------------------
# FFMPEG Process Management
# -------------------------------
processes = []
processes_lock = threading.Lock()
stop_flag = False
start_time = None


def start_ffmpeg_stream(index: int):
    """Start ffmpeg process"""
    cmd = FFMPEG_COMMAND.replace("${seq}", str(index))
    logging.info(f"Execute FFmpeg. seq: {index}, cmd: {cmd}")

    try:
        proc = subprocess.Popen(
            cmd.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Add to processes list immediately to ensure cleanup
        with processes_lock:
            processes.append(proc)
        logging.debug(
            f"FFmpeg process {index} started with PID: {proc.pid}, added to process list")

        # Wait briefly to check if process starts successfully
        time.sleep(0.5)

        # Check if process is still running
        if proc.poll() is not None:
            # Process has already terminated, remove from list
            with processes_lock:
                if proc in processes:
                    processes.remove(proc)

            stdout, stderr = proc.communicate()
            logging.error("=" * 60)
            logging.error(f"FFmpeg process {index} failed to start!")
            logging.error(f"Exit code: {proc.returncode}")
            logging.error(f"Command: {cmd}")

            if stdout:
                stdout_text = stdout.decode('utf-8', errors='ignore').strip()
                if stdout_text:
                    logging.error(f"STDOUT:\n{stdout_text}")

            if stderr:
                stderr_text = stderr.decode('utf-8', errors='ignore').strip()
                if stderr_text:
                    logging.error(f"STDERR:\n{stderr_text}")

            logging.error("=" * 60)
            return None
        else:
            logging.debug(
                f"FFmpeg process {index} verified successfully")
            return proc

    except FileNotFoundError:
        logging.error("=" * 60)
        logging.error(
            f"FFmpeg executable not found. Check if FFmpeg is installed and in PATH.")
        logging.error(f"Command attempted: {cmd}")
        logging.error("=" * 60)
        return None
    except Exception as e:
        logging.error("=" * 60)
        logging.error(f"Failed to start FFmpeg process {index}: {e}")
        logging.error(f"Command: {cmd}")
        logging.error("=" * 60)
        return None


def ffmpeg_runner():
    """Start one ffmpeg process every interval"""
    global stop_flag

    index = 0

    while not stop_flag:
        proc = start_ffmpeg_stream(index)

        if proc is None:
            logging.error(
                f"FFmpeg process {index} failed to start. Terminating program...")
            stop_flag = True
            os._exit(1)  # Exit with error code

        index += 1
        time.sleep(FFMPEG_EXECUTION_INTERVAL)


def stop_all_ffmpeg():
    """Stop all ffmpeg processes"""
    logging.info("Stopping all FFMPEG processes...")

    with processes_lock:
        processes_copy = processes.copy()
        processes.clear()

    for p in processes_copy:
        try:
            # Check if process exists and is running
            if p.poll() is None:
                os.kill(p.pid, signal.SIGTERM)
                logging.debug(f"Killed process {p.pid}")
            else:
                logging.debug(f"Process {p.pid} already terminated")
        except ProcessLookupError:
            logging.debug(f"Process {p.pid} not found (already terminated)")
        except Exception as e:
            logging.error(f"Error killing process {p.pid}: {e}")


def monitor_ffmpeg_processes():
    """Monitor running FFmpeg processes and log if they terminate unexpectedly"""
    global stop_flag

    while not stop_flag:
        time.sleep(2)  # Check every 2 seconds

        with processes_lock:
            # Use a copy to avoid modification during iteration
            processes_copy = processes.copy()

        for proc in processes_copy:
            if proc.poll() is not None:
                # Process has terminated
                returncode = proc.returncode

                if returncode != 0:
                    # Non-zero exit code indicates an error
                    try:
                        stdout, stderr = proc.communicate(timeout=1)

                        logging.warning("=" * 60)
                        logging.warning(
                            f"FFmpeg process (PID: {proc.pid}) terminated unexpectedly!")
                        logging.warning(f"Exit code: {returncode}")

                        if stdout:
                            stdout_text = stdout.decode(
                                'utf-8', errors='ignore').strip()
                            if stdout_text:
                                # Last 1000 chars
                                logging.warning(
                                    f"STDOUT:\n{stdout_text[-1000:]}")

                        if stderr:
                            stderr_text = stderr.decode(
                                'utf-8', errors='ignore').strip()
                            if stderr_text:
                                # Last 1000 chars
                                logging.warning(
                                    f"STDERR:\n{stderr_text[-1000:]}")

                        logging.warning("=" * 60)
                    except Exception as e:
                        logging.error(
                            f"Error reading terminated process output: {e}")


# -------------------------------
# HTTP Server Handler
# -------------------------------


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.startswith("/callback"):
            # Read and log the JSON payload
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                try:
                    payload = body.decode('utf-8')
                    logging.debug(f"Received callback payload: {payload}")

                    # Parse JSON and read 'type' key
                    payload_json = json.loads(payload)

                    alert_type = payload_json.get('type', 'N/A')

                    if alert_type == "INTERNAL_QUEUE" or alert_type == "EGRESS":

                        #  "messages": [
                        #     {
                        #     "code": "INTERNAL_QUEUE_CONGESTION",
                        #     "description": "Internal queue(s) is currently congested"
                        #     }
                        # ]
                        alert_messages = payload_json.get('messages', [])

                        # Check if any message has INTERNAL_QUEUE_CONGESTION code
                        for message in alert_messages:

                            alert_message_code = message.get('code', 'N/A')

                            if alert_message_code in MESSAGE_CODES:

                                global stop_flag
                                stop_flag = True

                                logging.info(
                                    f"{alert_type} - {alert_message_code} alert received. {message.get('description', 'No description')}")

                                with processes_lock:
                                    total_streams = len(processes)
                                test_duration = time.time() - start_time if start_time else 0

                                stop_all_ffmpeg()

                                logging.info("=" * 60)
                                logging.info("Test Results:")
                                logging.info(
                                    f"  - Alert message code: {alert_message_code}")
                                logging.info(
                                    f"  - Total Streams Started: {total_streams}")
                                logging.info(
                                    f"  - Test Duration: {test_duration:.2f} seconds")
                                logging.info("=" * 60)

                                # Send 200 response before exiting
                                self.send_response(200)
                                self.end_headers()

                                logging.debug("Program terminating...")
                                os._exit(0)

                except json.JSONDecodeError as e:
                    logging.error(f"Error parsing JSON: {e}")
                except Exception as e:
                    logging.error(f"Error decoding payload: {e}")
            else:
                logging.info(f"Received callback: {self.path} (no payload)")

            # Send 200 response for other cases (only if not already sent)
            if not hasattr(self, '_response_sent'):
                self.send_response(200)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress console log
        return


# -------------------------------
# Main Execution
# -------------------------------
if __name__ == "__main__":
    # Log configuration at startup
    logging.info("=" * 60)
    logging.info(f"Stress Tester for OvenMediaEngine v{VERSION}")
    logging.info("=" * 60)
    logging.info(f"Configuration:")
    logging.info(f"  - Log File: {LOG_FILE}")
    logging.info(
        f"  - Alert Callback Server Port: {ALERT_CALLBACK_SERVER_PORT}")
    logging.info(
        f"  - FFmpeg Execution Interval: {FFMPEG_EXECUTION_INTERVAL} seconds")
    logging.info(f"  - FFmpeg Command: {FFMPEG_COMMAND}")
    logging.info("=" * 60)

    # Start HTTP server first
    with socketserver.TCPServer(("", ALERT_CALLBACK_SERVER_PORT), CallbackHandler) as httpd:
        logging.info(
            f"Alert callback server running on port {ALERT_CALLBACK_SERVER_PORT}")

        # Record test start time
        start_time = time.time()

        # Start FFmpeg process monitor thread
        monitor_thread = threading.Thread(
            target=monitor_ffmpeg_processes, daemon=True)
        monitor_thread.start()
        logging.debug("FFmpeg process monitor started")

        # Start FFmpeg execution thread after server is ready
        thread = threading.Thread(target=ffmpeg_runner, daemon=True)
        thread.start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info("Received keyboard interrupt")
        finally:
            stop_flag = True
            stop_all_ffmpeg()
            logging.info("Server shutting down.")
