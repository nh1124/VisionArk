
import subprocess

def get_modified_files(cwd):
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd=cwd)
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"Error: {result.stderr}")

if __name__ == "__main__":
    import sys
    cwd = sys.argv[1] if len(sys.argv) > 1 else "."
    get_modified_files(cwd)
