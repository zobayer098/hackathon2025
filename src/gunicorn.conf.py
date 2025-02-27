import multiprocessing
import os
from typing import Dict
import asyncio
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import FilePurpose, FileSearchTool, AsyncToolSet
from azure.identity import DefaultAzureCredential

from dotenv import load_dotenv

load_dotenv()

async def list_or_create_agent():
    files: Dict[str, Dict[str, str]] = {}  # File name -> {"id": file_id, "path": file_path}
    vector_store = None
    agent = None

    try:
        ai_client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(exclude_shared_token_cache_credential=True),
            conn_str=os.environ["AZURE_AIPROJECT_CONNECTION_STRING"],
        )

        if os.environ.get("AZURE_AI_AGENT_ID"):
            try: 
                agent = await ai_client.agents.get_agent(os.environ["AZURE_AI_AGENT_ID"])
                return
            except Exception as e:
                print(f"Error fetching agent: {e}")

        # Check if a previous agent created by the template exists
        agent_list = await ai_client.agents.list_agents()
        if agent_list.data:
            for agent_object in agent_list.data:
                if agent_object.name == "agent-template-assistant":
                    return 
        
        # Create a new agent with the required resources
        print(f"Creating new agent with resources")
        file_names = ["product_info_1.md", "product_info_2.md"]
        for file_name in file_names:
            file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'files', file_name))
            file = await ai_client.agents.upload_file_and_poll(file_path=file_path, purpose=FilePurpose.AGENTS)
            # Store both file id and the file path using the file name as key.
            files[file_name] = {"id": file.id, "path": file_path}
        
        # Create the vector store using the file IDs.
        vector_store = await ai_client.agents.create_vector_store_and_poll(
            file_ids=[info["id"] for info in files.values()],
            name="sample_store"
        )
        print(f"agent: file store and vector store success")

        file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
        toolset = AsyncToolSet()
        toolset.add(file_search_tool)

        agent = await ai_client.agents.create_agent(
            model=os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"],
            name="agent-template-assistant", 
            instructions="You are helpful assistant",
            toolset=toolset
        )
        print(f"Created agent, agent ID: {agent.id}")
    
    except Exception as e:
        print(f"Error creating agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create the agent: {e}")
    
def on_starting(server):
    """This code runs once before the workers will start."""
    asyncio.get_event_loop().run_until_complete(list_or_create_agent())

max_requests = 1000
max_requests_jitter = 50
log_file = "-"
bind = "0.0.0.0:50505"

if not os.getenv("RUNNING_IN_PRODUCTION"):
    reload = True

preload_app = True
num_cpus = multiprocessing.cpu_count()
workers = (num_cpus * 2) + 1
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 120
