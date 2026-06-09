from zeropark_engines.sandbox import DockerSandbox

def test_docker():
    try:
        print("Initializing DockerSandbox...")
        sandbox = DockerSandbox()
        print("Success! Connected to Docker daemon.")
        
        # Test code execution
        code = """import os
import sys
print('OS User:', os.environ.get('USER', 'root'))
print('Platform:', sys.platform)
"""
        print(f"\nExecuting code:\n{code}")
        result = sandbox.execute(code)
        print(f"\nResult:\n{result}")
        
        if "root" in result and "linux" in result:
            print("TEST PASSED: Code ran successfully inside the isolated Linux container.")
        else:
            print("TEST WARNING: Unexpected output format.")
    except Exception as e:
        print(f"Docker is not available or error occurred: {e}")

if __name__ == "__main__":
    test_docker()
