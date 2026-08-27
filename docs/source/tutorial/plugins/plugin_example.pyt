#!/usr/bin/env python3
"""Example test that uses a plugin."""

import canary_pyt

# Basic test with plugin
canary_pyt.directives.keywords("tutorial", "plugin")
canary_pyt.directives.description("Test using a plugin")

def main():
    # Simple test logic
    print("Running test with plugin support")
    
    # The plugin hook would be called automatically by Canary
    # if the plugin is properly loaded
    print("✅ Test completed")

if __name__ == "__main__":
    main()