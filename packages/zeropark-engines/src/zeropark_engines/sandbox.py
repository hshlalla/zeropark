import io
import sys
import traceback
import contextlib
from typing import Any

try:
    import docker
except ImportError:
    docker = None


class PythonSandbox:
    """Executes python code locally in a captured environment.
    
    Warning: This is a simplistic local implementation for the MVP.
    In production, this must be replaced with a secured Docker container
    or a sandboxed execution environment to prevent RCE vulnerabilities.
    """

    def execute(self, code: str) -> str:
        """Executes the given python code and returns the stdout + stderr."""
        # Setup a string buffer to capture stdout
        captured_stdout = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_stdout

        # Isolated local namespace
        local_env: dict[str, Any] = {}

        result_str = ""
        try:
            # Execute the code block
            exec(code, {}, local_env)
            result_str = captured_stdout.getvalue()
            if not result_str.strip():
                result_str = "Execution completed successfully with no output."
        except Exception:
            # Capture the traceback if there's an error
            result_str = captured_stdout.getvalue()
            result_str += "\n" + traceback.format_exc()
        finally:
            sys.stdout = original_stdout
            captured_stdout.close()

        return result_str

class DockerSandbox:
    """Executes Python code in an isolated ephemeral Docker container."""
    def __init__(self, image: str = "python:3.11-slim", timeout: int = 15, mem_limit: str = "256m", allow_network: bool = False):
        self.image = image
        self.timeout = timeout
        self.mem_limit = mem_limit
        self.network_mode = "bridge" if allow_network else "none"
        if docker is None:
            raise ImportError("docker package is not installed. Please 'pip install docker'")
        self.client = docker.from_env()

    def execute(self, code: str) -> str:
        """Executes code in Docker and returns stdout/stderr."""
        try:
            # Escape single quotes for bash inline execution
            escaped_code = code.replace("'", "'\\''")
            cmd = f"python -c '{escaped_code}'"
            
            output = self.client.containers.run(
                image=self.image,
                command=cmd,
                remove=True,  # Automatically remove container when it exits
                mem_limit=self.mem_limit,
                network_mode=self.network_mode,
            )
            return output.decode("utf-8")
        except Exception as e:
            # Handle container error which has stderr
            if hasattr(e, 'stderr') and e.stderr is not None:
                return f"Sandbox Container Error:\n{e.stderr.decode('utf-8')}"
            return f"Sandbox Execution Failed: {str(e)}"
