from mcp_server import _build_multi_table_prompt, connect_database

connect_database(database_name='anandrathi')

prompt = _build_multi_table_prompt(
    question="how many errors are there for each application",
    table_names=["CommunicationMaster", "CommunicationErrorMaster", "ApplicationMaster"],
    category_name="Communications"
)
print(prompt)