"""Console entry point; desktop GUI builds do not provide stdin/stdout pipes."""
from artlib.mcp_server import main

if __name__ == '__main__':
    main()
