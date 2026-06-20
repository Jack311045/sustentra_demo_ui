from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()

response = client.responses.create(
    model="gpt-5.4",
    input="Reply with exactly: OpenAI connection works."
)

print(response.output_text)