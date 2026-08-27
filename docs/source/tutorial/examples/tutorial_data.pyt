#!/usr/bin/env python3
"""Simple data processing tutorial example."""

import canary_pyt

# Data processing test
canary_pyt.directives.keywords("tutorial", "data")
canary_pyt.directives.copy("input.txt")

def main():
    # Read input file
    with open("input.txt", "r") as f:
        data = f.read()
    
    # Simple processing
    result = data.upper()
    
    # Write output
    with open("output.txt", "w") as f:
        f.write(result)
    
    # Simple output
    print(f"Processed {len(data)} characters")
    print(f"Result: {result[:50]}...")

if __name__ == "__main__":
    main()