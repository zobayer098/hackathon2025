# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

import contextlib
import logging
import os
import sys
from typing import Dict

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import FilePurpose, FileSearchTool, AsyncToolSet
from azure.identity import DefaultAzureCredential

import fastapi
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Create a central logger for the application
logger = logging.getLogger("azureaiapp")
logger.setLevel(logging.INFO)

# Configure the stream handler (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

# Configure logging to file, if log file name is provided
log_file_name = os.getenv("APP_LOG_FILE")
if log_file_name is not None:
    file_handler = logging.FileHandler(log_file_name)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

enable_trace_string = os.getenv("ENABLE_AZURE_MONITOR_TRACING")
enable_trace = False
if enable_trace_string is None:
    enable_trace = False
else:
    enable_trace = str(enable_trace_string).lower() == "true"
if enable_trace:
    logger.info("Tracing is enabled.")
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ModuleNotFoundError:
        logger.error("Required libraries for tracing not installed.")
        logger.error("Please make sure azure-monitor-opentelemetry is installed.")
        exit()
else:
    logger.info("Tracing is not enabled")

@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    files: Dict[str, Dict[str, str]] = {}  # File name -> {"id": file_id, "path": file_path}
    vector_store = None
    agent = None
    create_new_agent = True

    try:
        if not os.getenv("RUNNING_IN_PRODUCTION"):
            logger.info("Loading .env file")
            load_dotenv(override=True)

        ai_client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(exclude_shared_token_cache_credential=True),
            conn_str=os.environ["AZURE_AIPROJECT_CONNECTION_STRING"],
        )
        logger.info("Created AIProjectClient")

        if enable_trace:
            application_insights_connection_string = ""
            try:
                application_insights_connection_string = await ai_client.telemetry.get_connection_string()
            except Exception as e:
                e_string = str(e)
                logger.error("Failed to get Application Insights connection string, error: %s", e_string)
            if not application_insights_connection_string:
                logger.error("Application Insights was not enabled for this project.")
                logger.error("Enable it via the 'Tracing' tab in your AI Foundry project page.")
                exit()
            else:
                configure_azure_monitor(connection_string=application_insights_connection_string)

        if os.environ.get("AZURE_AI_AGENT_ID") is not None:
            try: 
                agent = await ai_client.agents.get_agent(os.environ["AZURE_AI_AGENT_ID"])
                create_new_agent = False
                logger.info("Agent already exists, skipping creation")
                logger.info(f"Fetched agent, agent ID: {agent.id}")
                logger.info(f"Fetched agent, model name: {agent.model}")
            except Exception as e:
                logger.error(f"Error fetching agent: {e}", exc_info=True)
                create_new_agent = True
        if create_new_agent:
            logger.info("Creating agent")
            file_names = ["product_info_1.md", "product_info_2.md"]
            for file_name in file_names:
                file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'files', file_name))
                file = await ai_client.agents.upload_file_and_poll(file_path=file_path, purpose=FilePurpose.AGENTS)
                logger.info(f"Uploaded file {file_path}, file ID: {file.id}")
                # Store both file id and the file path using the file name as key.
                files[file_name] = {"id": file.id, "path": file_path}
            
            # Create the vector store using the file IDs.
            vector_store = await ai_client.agents.create_vector_store_and_poll(
                file_ids=[info["id"] for info in files.values()],
                name="sample_store"
            )

            file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
            toolset = AsyncToolSet()
            toolset.add(file_search_tool)

            agent = await ai_client.agents.create_agent(
                model=os.environ["AZURE_AI_CHAT_DEPLOYMENT_NAME"],
                name="my-assistant", 
                instructions="You are helpful assistant",
                toolset=toolset
            )
        
            logger.info(f"Created agent, agent ID: {agent.id}")
            logger.info(f"Created agent, model name: {agent.model}")

    except Exception as e:
        logger.error(f"Error creating agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create the agent: {e}")

    app.state.ai_client = ai_client
    app.state.agent = agent
    app.state.files = files

    try:
        yield
    finally:
        # Cleanup on shutdown.
        if create_new_agent:
            try:
                for info in files.values():
                    await ai_client.agents.delete_file(info["id"])
                    logger.info(f"Deleted file {info['id']}")
                
                if vector_store:
                    await ai_client.agents.delete_vector_store(vector_store.id)
                    logger.info(f"Deleted vector store {vector_store.id}")

                if agent:
                    await ai_client.agents.delete_agent(agent.id)
                    logger.info(f"Deleted agent {agent.id}")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True)

        try:
            await ai_client.close()
            logger.info("Closed AIProjectClient")
        except Exception as e:
            logger.error("Error closing AIProjectClient", exc_info=True)


def create_app():
    directory = os.path.join(os.path.dirname(__file__), "static")
    app = fastapi.FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=directory), name="static")

    from . import routes  # Import routes
    app.include_router(routes.router)

    # Global exception handler for any unhandled exceptions
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception occurred", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    
    return app
