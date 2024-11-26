# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

from typing import Any, AsyncGenerator, Optional, Tuple
from quart import Blueprint, jsonify, request, Response, render_template, current_app

import asyncio
import json, os

import os
from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential

from azure.ai.projects.models import (
    MessageDeltaTextContent,
    MessageDeltaChunk,
    ThreadMessage,
    FileSearchTool,
    AsyncToolSet,
    FilePurpose,
    ThreadMessage,
    ThreadError,
    StreamEventData,
    AgentStreamEvent
)

bp = Blueprint("chat", __name__, template_folder="templates", static_folder="static")


@bp.before_app_serving
async def start_server():
    
    ai_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(exclude_shared_token_cache_credential=True),
        conn_str=os.environ["PROJECT_CONNECTION_STRING"],
    )
    
    # TODO: add more files are not supported for citation at the moment
    files = ["product_info_1.md"]
    file_ids = []
    for file in files:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'files', file))
        print(f"Uploading file {file_path}")
        file = await ai_client.agents.upload_file_and_poll(file_path=file_path, purpose=FilePurpose.AGENTS)
        file_ids.append(file.id)
    
    vector_store = await ai_client.agents.create_vector_store(file_ids=file_ids, name="sample_store")

    file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
    
    tool_set = AsyncToolSet()
    tool_set.add(file_search_tool)
    
    print(f"ToolResource: {tool_set.resources}")
        
    agent = await ai_client.agents.create_agent(
        model="gpt-4o-mini", name="my-assistant", instructions="You are helpful assistant", tools = tool_set.definitions, tool_resources=tool_set.resources
    )
    
    print(f"Created agent, agent ID: {agent.id}")

    bp.ai_client = ai_client
    bp.agent = agent
    bp.vector_store = vector_store
    bp.file_ids = file_ids
        

@bp.after_app_serving
async def stop_server():
    for file_id in bp.file_ids:
        await bp.ai_client.agents.delete_file(file_id)
        print(f"Deleted file {file_id}")
    
    await bp.ai_client.agents.delete_vector_store(bp.vector_store.id)
    print(f"Deleted vector store {bp.vector_store.id}")
    
    await bp.ai_client.agents.delete_agent(bp.agent.id)

    print(f"Deleted agent {bp.agent.id}")        
    
    await bp.ai_client.close()
    print("Closed AIProjectClient")

async def yield_callback(event_type: str, event_obj: StreamEventData, **kwargs) -> Optional[str]:
    accumulated_text = kwargs['accumulated_text']
    if (isinstance(event_obj, MessageDeltaTextContent)):
        text_value = event_obj.text.value if event_obj.text else "No text"
        stream_data = json.dumps({'content': text_value, 'type': "message"})
        accumulated_text[0] += text_value
        return f"data: {stream_data}\n\n"
    elif isinstance(event_obj, ThreadMessage):
        if (event_obj.status == "completed"):
            stream_data = json.dumps({'content': accumulated_text[0], 'type': "completed_message"})
            return f"data: {stream_data}\n\n"
    elif isinstance(event_obj, ThreadError):
        print(f"An error occurred. Data: {event_obj.error}")
        stream_data = json.dumps({'type': "stream_end"})
        return f"data: {stream_data}\n\n"
    elif event_type == AgentStreamEvent.DONE:
        stream_data = json.dumps({'type': "stream_end"})
        return f"data: {stream_data}\n\n"
           
    return None
@bp.get("/")
async def index():
    return await render_template("index.html")

    

async def get_result(thread_id: str, agent_id: str):
    
    accumulated_text = [""]
    
    async with await bp.ai_client.agents.create_stream(
        thread_id=thread_id, assistant_id=agent_id,
    ) as stream:
        async for to_be_yield in stream.yield_until_done(yield_callback, accumulated_text=accumulated_text):
            yield to_be_yield
                
@bp.route('/chat', methods=['POST'])
async def chat():
    thread_id = request.cookies.get('thread_id')
    agent_id = request.cookies.get('agent_id')
    thread = None
    
    if thread_id or agent_id != bp.agent.id:
        # Check if the thread is still active
        try:
            thread = await bp.ai_client.agents.get_thread(thread_id)
        except Exception as e:
            current_app.logger.error(f"Failed to retrieve thread with ID {thread_id}: {e}")
    if thread is None:
        thread = await bp.ai_client.agents.create_thread()    
                    
    thread_id = thread.id
    agent_id = bp.agent.id    
    user_message = await request.get_json()

    if not hasattr(bp, 'ai_client'):
        return jsonify({"error": "Agent is not initialized"}), 500

    message = await bp.ai_client.agents.create_message(
        thread_id=thread.id, role="user", content=user_message['message']
    )
    print(f"Created message, message ID {message.id}")


    # Set necessary headers for SSE
    headers = {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Content-Type': 'text/event-stream'
    }

    response = Response(get_result(thread_id, agent_id), headers=headers)
    response.set_cookie('thread_id', thread_id)
    response.set_cookie('agent_id', agent_id)    
    return response

@bp.route('/fetch-document', methods=['GET'])
async def fetch_document():
    filename = "product_info_1.md"

    # Get the file path from the mapping
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'files', filename))
    
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {filename}"}), 404

    try:
        # Read the file content asynchronously using asyncio.to_thread
        data = await asyncio.to_thread(read_file, file_path)
        return Response(data, content_type='text/plain')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def read_file(path):
    with open(path, 'r') as file:
        return file.read()
