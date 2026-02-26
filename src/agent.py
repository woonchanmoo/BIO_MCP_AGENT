from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import tools_condition
from typing import Annotated, TypedDict, Any, Sequence
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from dotenv import load_dotenv

load_dotenv()

# 1. 실제 에러를 처리할 함수 정의 (이름은 자유)
def handle_tool_error(error: Exception) -> str:
    print(f"--- [🔴 Tool Error Log 🔴] ---\n{repr(error)}\n------------------------")
    return f"Error: {repr(error)}."

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    error_count: int


FILESYSTEM_TOOL_NAMES = {
    "list_directory",
    "read_file",
    "write_file",
    "create_directory",
    "move_file",
    "search_files",
    "get_file_info",
    "list_allowed_directories",
    "read_multiple_files",
}


def normalize_filesystem_args(tool_name: str, tool_args: Any) -> Any:
    if tool_name not in FILESYSTEM_TOOL_NAMES or not isinstance(tool_args, dict):
        return tool_args

    normalized = dict(tool_args)

    if "path" not in normalized:
        for alias in ("directory_path", "dir_path", "file_path", "folder_path"):
            if isinstance(normalized.get(alias), str):
                normalized["path"] = normalized[alias]
                break

    if tool_name == "list_directory" and not isinstance(normalized.get("path"), str):
        normalized["path"] = "."

    if tool_name == "list_directory" and normalized.get("path", "") == "":
        normalized["path"] = "."

    return normalized

def build_simple_agent(model: str, system_prompt: str, tools: Sequence[Any], checkpointer = None):
    llm = init_chat_model(model=model)
    llm_with_tools = llm.bind_tools(tools)
    tool_by_name = {tool.name: tool for tool in tools}

    async def agent_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        current_errors = state.get("error_count", 0)

        # 🌟 [핵심 추가] 사용자가 새로운 입력을 했다면 에러 카운트를 0으로 초기화
        # 마지막 메시지가 HumanMessage라면 사용자가 새로운 시도를 하려는 것이므로 카운트를 리셋합니다.
        # 1. 새로운 질문 시 완전 초기화 후 즉시 모델 호출로 점프
        if messages and isinstance(messages[-1], HumanMessage):
            current_errors = 0
            # 과거 에러 계산 루프를 타지 않고 바로 모델 호출로 넘깁니다.
            llm_input = [SystemMessage(content=system_prompt), *messages]
            response = await llm_with_tools.ainvoke(llm_input)
            # (로그 출력 로직 생략)
            return {"messages": [response], "error_count": 0}

        # 2. 툴 결과에 대한 에러 계산 (사용자 질문이 아닐 때만 이 아래가 실행됨)
        new_errors = 0
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                if "Error:" in msg.content:
                    new_errors += 1
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                break

        if new_errors > 0:
            current_errors += new_errors
        else:
            # 마지막 메시지가 성공한 툴 결과라면 초기화
            if messages and isinstance(messages[-1], ToolMessage):
                current_errors = 0

        # 3. 임계치 체크
        if current_errors >= 5:
            return {
                "messages": [AIMessage(content="🔴 다수의 도구 호출에서 연속적인 오류가 발생했습니다.")],
                "error_count": current_errors
            }
        
        # 4. 모델 호출 (툴 결과를 보고 다시 판단해야 할 때)
        llm_input = [SystemMessage(content=system_prompt), *messages]
        response = await llm_with_tools.ainvoke(llm_input)

        # # 4. 🔥 [최종 로그 확인 영역] 🔥
        # print("\n\n" + "📜" + "="*30 + " FULL CONVERSATION LOG " + "="*30)
        # for i, msg in enumerate(messages + [response]):
        #     role = f"[{msg.type.upper()}]"
            
        #     # 메시지 유형별 색상/이름 정의 (터미널 가독성)
        #     if isinstance(msg, HumanMessage):
        #         header = f"\033[92m{role} User:\033[0m" # 초록
        #     elif isinstance(msg, AIMessage):
        #         header = f"\033[94m{role} AI (Scout):\033[0m" # 파랑
        #     elif isinstance(msg, ToolMessage):
        #         header = f"\033[93m{role} Tool Result:\033[0m" # 노랑
        #     else:
        #         header = role

        #     content = msg.content if msg.content else "(No text content)"
            
        #     # 도구 호출 정보가 있으면 추가 출력
        #     tool_info = ""
        #     if isinstance(msg, AIMessage) and msg.tool_calls:
        #         tool_info = f" 🛠️ Calls: {[tc['name'] for tc in msg.tool_calls]}"

        #     print(f"{i:02d} {header}{tool_info}")
        #     # 너무 길면 150자만 출력
        #     print(f"   Content: {str(content)[:150]}..." if len(str(content)) > 150 else f"   Content: {content}")
        # print(f"\n📊 Current Status - Error Count: {current_errors}")
        # print("="*85 + "\n")

        # 여기서 직접 print하지 않고 response만 반환합니다.
        return {
            "messages": [response],
            "error_count": current_errors}
    
    workflow = StateGraph(AgentState)

    async def tools_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        if not messages:
            return {"messages": [], "error_count": state.get("error_count", 0)}

        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": [], "error_count": state.get("error_count", 0)}

        tool_results: list[ToolMessage] = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_call_id = tool_call.get("id", "")
            raw_args = tool_call.get("args", {})
            tool_args = normalize_filesystem_args(tool_name, raw_args)

            tool = tool_by_name.get(tool_name)
            if tool is None:
                error_text = handle_tool_error(Exception(f"Tool not found: {tool_name}"))
                tool_results.append(ToolMessage(content=error_text, tool_call_id=tool_call_id, name=tool_name))
                continue

            try:
                result = await tool.ainvoke(tool_args)
                if isinstance(result, ToolMessage):
                    content = result.content
                elif isinstance(result, str):
                    content = result
                else:
                    content = str(result)
            except Exception as error:
                content = handle_tool_error(error)

            tool_results.append(ToolMessage(content=content, tool_call_id=tool_call_id, name=tool_name))

        return {"messages": tool_results, "error_count": state.get("error_count", 0)}

    workflow.add_node("Agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_edge(START, "Agent")
    workflow.add_conditional_edges(
        "Agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END
        }
    )
    workflow.add_edge("tools", "Agent")

    return workflow.compile(checkpointer=checkpointer)
