import os
import pty
import shlex
import select
import subprocess
import time
from typing import Optional, Callable
from src.core.config import system_logger

class ObservedPtyRunner:
    """
    Executes shell commands within a PTY (Pseudoterminal) to capture 
    rich console output and provide real-time observation.
    """

    def __init__(
        self, 
        on_data: Optional[Callable[[str], None]] = None,
        timeout_seconds: int = 60
    ):
        self.on_data = on_data
        self.timeout_seconds = timeout_seconds
        self.output_buffer = []

    def run(self, command: str, cwd: str = ".") -> dict:
        """
        Runs a command string in a PTY and blocks until completion or timeout.
        """
        system_logger.info(f"ObservedPtyRunner: Executing '{command}' in {cwd}")
        
        # Reset state for this run
        self.output_buffer = []

        # Run command via bash -c to support pipes, redirects, etc.
        argv = ["/bin/bash", "-c", command]

        # Fork a pty
        master_fd, slave_fd = pty.openpty()
        
        start_time = time.time()
        process = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            close_fds=True,
            start_new_session=True
        )

        # Close slave side in parent
        os.close(slave_fd)

        # Non-blocking read loop
        os.set_blocking(master_fd, False)
        
        try:
            while process.poll() is None:
                # Check for timeout
                if time.time() - start_time > self.timeout_seconds:
                    process.terminate()
                    return {
                        "status": "timeout_failure",
                        "stdout": "".join(self.output_buffer),
                        "stderr": "Execution timed out.",
                        "returncode": -1
                    }

                # Read available data
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if r:
                    try:
                        data = os.read(master_fd, 1024).decode("utf-8", errors="replace")
                        if data:
                            self.output_buffer.append(data)
                            if self.on_data:
                                self.on_data(data)
                    except (OSError, EOFError):
                        break
                
                # Small sleep to prevent busy-waiting if select returns fast
                time.sleep(0.01)

            # Final read after process exit
            while True:
                r, _, _ = select.select([master_fd], [], [], 0)
                if r:
                    try:
                        data = os.read(master_fd, 1024).decode("utf-8", errors="replace")
                        if not data:
                            break
                        self.output_buffer.append(data)
                        if self.on_data:
                            self.on_data(data)
                    except:
                        break
                else:
                    break

        finally:
            os.close(master_fd)

        return {
            "status": "success" if process.returncode == 0 else "failed",
            "stdout": "".join(self.output_buffer),
            "stderr": "",
            "returncode": process.returncode
        }
