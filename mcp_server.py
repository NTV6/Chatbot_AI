from fastmcp import FastMCP
from ai_service.rag import query_docs

mcp = FastMCP("RAGTools")

@mcp.tool()
def search_documents(question: str):
    print("MCP TOOL CALLED")
    return query_docs(question)

@mcp.tool()
def get_server_status():
    return "Server is running"

if __name__ == "__main__":
    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=8001
    )