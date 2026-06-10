import io
import os
import sys
import traceback
from typing import Any

try:
    import docker
except ImportError:
    docker = None


def unsafe_sandbox_allowed() -> bool:
    """The local exec() sandbox is RCE-by-design; it must be explicitly opted in."""
    return os.environ.get("ZEROPARK_ALLOW_UNSAFE_SANDBOX", "").lower() in ("1", "true", "yes")


class PythonSandbox:
    """Executes python code locally with exec(). NOT a security boundary.

    Only usable when ZEROPARK_ALLOW_UNSAFE_SANDBOX=1 (local development).
    Production deployments must use DockerSandbox.
    """

    def __init__(self) -> None:
        if not unsafe_sandbox_allowed():
            raise PermissionError(
                "PythonSandbox executes arbitrary code in-process. "
                "Set ZEROPARK_ALLOW_UNSAFE_SANDBOX=1 to enable it for local development, "
                "or run Docker so DockerSandbox can be used."
            )

    def execute(self, code: str) -> str:
        """Executes the given python code and returns the stdout + stderr."""
        captured_stdout = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_stdout

        local_env: dict[str, Any] = {}

        result_str = ""
        try:
            exec(code, {}, local_env)
            result_str = captured_stdout.getvalue()
            if not result_str.strip():
                result_str = "Execution completed successfully with no output."
        except Exception:
            result_str = captured_stdout.getvalue()
            result_str += "\n" + traceback.format_exc()
        finally:
            sys.stdout = original_stdout
            captured_stdout.close()

        return result_str


class DockerSandbox:
    """Executes Python code in an isolated ephemeral Docker container.

    Code is passed as an argv element (no shell interpolation), the container
    has no network by default, a memory cap, and a hard wall-clock timeout
    enforced via detach + wait.
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 15,
        mem_limit: str = "256m",
        allow_network: bool = False,
    ):
        self.image = image
        self.timeout = timeout
        self.mem_limit = mem_limit
        self.network_mode = "bridge" if allow_network else "none"
        if docker is None:
            raise ImportError("docker package is not installed. Please 'pip install docker'")
        self.client = docker.from_env()
        self.client.ping()  # fail fast if the daemon is unreachable

    def execute(self, code: str) -> str:
        """Executes code in Docker and returns stdout/stderr."""
        container = None
        try:
            # argv-style command: the code never passes through a shell.
            container = self.client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                detach=True,
                mem_limit=self.mem_limit,
                network_mode=self.network_mode,
            )
            try:
                exit_info = container.wait(timeout=self.timeout)
            except Exception:
                container.kill()
                return f"Sandbox Timeout: execution exceeded {self.timeout}s and was killed."
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            status_code = exit_info.get("StatusCode", -1)
            if status_code != 0:
                return f"Sandbox Container Error (exit {status_code}):\n{logs}"
            return logs if logs.strip() else "Execution completed successfully with no output."
        except Exception as e:
            return f"Sandbox Execution Failed: {e}"
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
