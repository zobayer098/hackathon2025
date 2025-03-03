# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license.
# See LICENSE file in the project root for full license information.
import asyncio
import multiprocessing
import os
from typing import Dict
import asyncio
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import FilePurpose, FileSearchTool, AsyncToolSet
from azure.identity import DefaultAzureCredential

from azure.identity.aio import DefaultAzureCredential


async def create_index_maybe():
    """
    Create the index and upload documents if the index does not exist.

    This code is executed only once, when called on_starting hook is being
    called. This code ensures that the index is being populated only once.
    rag.create_index return True if the index was created, meaning that this
    docker node have started first and must populate index.
    """
    from api.search_index_manager import SearchIndexManager
    async with DefaultAzureCredential() as creds:
        endpoint = os.environ.get('AZURE_AI_SEARCH_ENDPOINT')
        if endpoint:
            search_mgr = SearchIndexManager(
                endpoint=endpoint,
                credential=creds,
                index_name=os.getenv('AZURE_AI_SEARCH_INDEX_NAME'),
                dimensions=None,
                model=os.getenv('AZURE_AI_EMBED_DEPLOYMENT_NAME'),
                embeddings_client=None
            )
            # If another application instance already have created the index,
            # do not upload the documents.
            if await search_mgr.create_index(
              vector_index_dimensions=int(
                  os.getenv('AZURE_AI_EMBED_DIMENSIONS'))):
                embeddings_path = os.path.join(
                    os.path.dirname(__file__), 'api', 'data', 'embeddings.csv')
                assert embeddings_path, f'File {embeddings_path} not found.'
                await search_mgr.upload_documents(embeddings_path)
                await search_mgr.close()


async def init_agent_and_index():
    files: Dict[str, Dict[str, str]] = {}  # File name -> {"id": file_id, "path": file_path}
    vector_store = None
    agent = None
    await create_index_maybe()

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
        
        # Add the AI index search.
        conn_list = ai_client.connections.list()
        conn_id = ""
        for conn in conn_list:
            if conn.connection_type == ConnectionType.AZURE_AI_SEARCH:
                conn_id = conn.id
                break

        toolset = None
        tool_definitions = None
        if conn_id and os.environ.get('AZURE_AI_SEARCH_INDEX_NAME'):
            ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name=os.environ.get('AZURE_AI_SEARCH_INDEX_NAME'))
            toolset = AsyncToolSet()
            toolset.add(ai_search)
            tool_definitions = ai_search.definitions

        agent = await ai_client.agents.create_agent(
            model=os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"],
            name="agent-template-assistant", 
            instructions="You are helpful assistant",
            tools=ai_search.definitions,
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

# Load application code before the worker processes are forked.
# Needed to execute on_starting.
# Please see the documentation on gunicorn
# https://docs.gunicorn.org/en/stable/settings.html
preload_app = True
num_cpus = multiprocessing.cpu_count()
workers = (num_cpus * 2) + 1
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 120
