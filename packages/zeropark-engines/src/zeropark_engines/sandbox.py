import io
import sys
import traceback
from typing import Any


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
