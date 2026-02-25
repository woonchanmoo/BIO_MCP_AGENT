from langchain_mcp_adapters.client import MultiServerMCPClient
from src.agent import build_simple_agent
from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from langgraph.checkpoint.memory import MemorySaver
import asyncio
import warnings
from src.prompt import BASE_SYSTEM_PROMPT
from src.config.config import MCP_CONFIG, MCP_FILESYSTEM_DIR, LLM_MODEL
from prompt_toolkit import prompt as pt_prompt

warnings.filterwarnings("ignore", category=UserWarning)

async def get_multiline_input(prompt: str) -> str:
    # \033[96m: Cyan색, \033[1m: Bold, \033[0m: Reset
    guide = "\033[96m\033[1m(전송: Esc 누른 후 Enter)\033[0m"
    print(f"{prompt} {guide}")
    # multiline=True일 때, 전송은 보통 'Esc' 누른 후 'Enter' 또는 'Meta+Enter'
    # 혹은 마우스로 클릭할 수 없는 환경이므로 안내 메시지가 필요합니다.
    user_input = await asyncio.to_thread(
        pt_prompt, 
        "> ", 
        multiline=True,
        prompt_continuation="  " # 줄바꿈 시 앞에 붙는 접두어
    )
    return user_input.strip()

async def stream_graph_response(input, graph, config={}):
    last_index = -1
    first_text = True

    async for message_chunk, metadata in graph.astream(
        input=input, stream_mode="messages", config=config
    ):
        # 도구 실행 노드에서 나오는 출력은 중복이므로 건너뜁니다.
        if metadata.get("langgraph_node") == "tools":
            continue

        # 1. AIMessage(완성본) 또는 AIMessageChunk(조각)인지 확인
        if isinstance(message_chunk, (AIMessage, AIMessageChunk)):
            
            # 2. 도구 호출(Tool Calls) 처리
            # Chunk 타입이고 tool_call_chunks가 있는 경우에만 실행
            if isinstance(message_chunk, AIMessageChunk) and message_chunk.tool_call_chunks:
                for chunk in message_chunk.tool_call_chunks:
                    idx = chunk.get("index")
                    if idx != last_index:
                        if chunk.get("name"):
                            yield f"\n\033[94m🛠️  Executing Tool: {chunk['name']}\033[0m\n"
                            last_index = idx
                    if chunk.get("args"):
                        yield f"\033[90m{chunk['args']}\033[0m"
            
            # 3. 일반 텍스트 내용(Content) 출력
            # 완성된 AIMessage(에러 중단 메시지 포함)와 Chunk의 텍스트를 모두 잡습니다.
            elif message_chunk.content:
                if first_text:
                    yield "\n\033[1;32m[AI]:\033[0m " 
                    first_text = False
                
                # content가 리스트 형태인 경우(멀티모달 등)를 대비해 문자열 변환
                content_text = message_chunk.content if isinstance(message_chunk.content, str) else str(message_chunk.content)
                yield content_text

            # 4. 마무리 처리 (Chunk의 finish_reason 확인)
            if isinstance(message_chunk, AIMessageChunk):
                if message_chunk.response_metadata.get("finish_reason") == "tool_calls":
                    yield "\n"
                    last_index = -1

async def run_mcp_agent():

    # Memory Configuration
    memory = MemorySaver()
    config = {
        "configurable": {"thread_id": "thread_1"},
        "recursion_limit": 300} # 50번 이상의 도구 사용 가능

    # MCP Server Connection
    try:
        print("CONNECTING MCP SERVER...")
        from src.config.config import MCP_CONFIG as config_dict
        print(f"📋 MCP Config contains {len(config_dict)} servers:")
        for server_name in config_dict.keys():
            print(f"   - {server_name}")
        
        client = MultiServerMCPClient(MCP_CONFIG)
        print("⏳ Loading tools from servers...")
        # 이 단계에서 서버가 안 뜨면 무한 대기하거나 죽을 수 있습니다.
        tools = await asyncio.wait_for(client.get_tools(), timeout=120.0) 
    except asyncio.TimeoutError:
        print("❌ MCP 서버 연결 타임아웃!")
        return
    except Exception as e:
        import traceback
        print(f"❌ 연결 중 오류 발생: {e}")
        print("📋 Error trace:")
        traceback.print_exc()
        return

    if not tools:
        print("❌ MCP 도구를 로드하지 못했습니다.")
        return
    
    print(f"✅ Loaded {len(tools)} tools.")

    system_prompt = f"""
    Your name is Scout and you are an expert data scientist.
    You help customers manage their data science projects by leveraging the tools available to you.
    Your goal is to collaborate with the customer in incrementally building their analysis or data modeling project.

    <filesystem>
    You have access to a set of tools that allow you to interact with the user's local filesystem. 
    You are only able to access files within the working directory `mcp_workspace`.
    The absolute path to this directory is: {MCP_FILESYSTEM_DIR}
    If you try to access a file outside of this directory, you will receive an error.
    Prefer relative paths from this root (for example: `inputs/data`, `runs/Q1/attempt3`, `docs`).
    </filesystem>

    {BASE_SYSTEM_PROMPT}

    <tools>
    {tools}
    </tools>

    Assist the customer in all aspects of their data science workflow.
    """
    
    # Agent Initialization
    mcp_agent = build_simple_agent(
        model=LLM_MODEL,
        system_prompt=system_prompt,
        tools=tools,
        checkpointer=memory
    )

    print("\n--- MCP Agent Started ---")
    print("종료하려면 'exit' 또는 'quit'을 입력하세요.")

    # 2. 반복 루프 시작
    while True:
        user_input = await get_multiline_input("\n[User]: ")

        if user_input.lower() in ["exit", "quit"]:
            print("👋 프로그램을 종료합니다.")
            break

        if not user_input:
            continue

        msg = {
            "messages": [HumanMessage(content=user_input)]
        }

        try:
            print("\n🤖 ...", end="\n\n", flush=True)
            
            # 통합된 제너레이터 호출
            async for text in stream_graph_response(msg, mcp_agent, config):
                print(text, end="", flush=True)
            
            print("\n")
        
        except Exception as e:
                    # 이제 여기는 '그래프 내부' 에러가 아니라 '시스템 레벨' 에러만 잡힙니다.
                    print(f"\n\033[91m🔴 치명적 시스템 오류 발생: {e}\033[0m")
                    # 필요하다면 여기서만 아주 제한적으로 메모리 초기화를 고려할 수 있습니다.

if __name__ == "__main__":
    # 터미널 실행 시에는 아래 두 줄이 없어도 되지만, 노트북 환경 호환성을 위해 유지 가능
    import nest_asyncio
    nest_asyncio.apply()

    try:
        # 비동기 에이전트 실행 루프
        asyncio.run(run_mcp_agent())
    except KeyboardInterrupt:
        print("\n강제 종료되었습니다.")
