import subprocess
import json

# Run the CLI tool directly as a single command line execution
cmd = "npx atlascloud-mcp list-models --type Image-to-Image"

print("Querying Atlas Cloud...")

# Execute and capture the direct string output
result = subprocess.run(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    shell=True
)

# Print the results
if result.returncode == 0:
    print("\n--- Model List ---")
    print(result.stdout)
else:
    print("\n--- Error ---")
    print(result.stderr)