import boto3  

client = boto3.client("bedrock-runtime", region_name="ap-south-2")

response = client.converse_stream( 
    modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0", 
    messages=[
        { 
            "role": "user", 
            "content": [{"text": "Tell me a short story about a robot."}]
        }
    ]
)

for event in response["stream"]: 
    if "contentBlockDelta" in event: 
        delta = event["contentBlockDelta"]["delta"] 
        if "text" in delta: 
            print(delta["text"], end="", flush=True)