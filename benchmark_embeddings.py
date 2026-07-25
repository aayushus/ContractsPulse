import asyncio
import time

class MockEmbeddings:
    async def create(self, model, input):
        await asyncio.sleep(0.5) # Simulate network delay
        class MockResponse:
            def __init__(self, size):
                class Item:
                    def __init__(self):
                        self.embedding = [0.1, 0.2, 0.3]
                self.data = [Item() for _ in range(size)]
        return MockResponse(len(input))

class MockClient:
    def __init__(self):
        self.embeddings = MockEmbeddings()

client = MockClient()
texts = ["text"] * 500 # 500 texts -> 5 chunks of 100

async def sequential():
    start = time.time()
    embeddings = []
    for i in range(0, len(texts), 100):
        chunk = texts[i:i+100]
        res = await client.embeddings.create(
            model="text-embedding-3-small",
            input=chunk
        )
        embeddings.extend([item.embedding for item in res.data])
    end = time.time()
    return end - start

async def concurrent():
    start = time.time()
    chunks = [texts[i:i+100] for i in range(0, len(texts), 100)]
    tasks = [client.embeddings.create(model="text-embedding-3-small", input=chunk) for chunk in chunks]
    responses = await asyncio.gather(*tasks)
    embeddings = []
    for res in responses:
        embeddings.extend([item.embedding for item in res.data])
    end = time.time()
    return end - start

async def main():
    seq_time = await sequential()
    print(f"Sequential time: {seq_time:.2f}s")

    conc_time = await concurrent()
    print(f"Concurrent time: {conc_time:.2f}s")

    if seq_time > 0:
        improvement = (seq_time - conc_time) / seq_time * 100
        print(f"Improvement: {improvement:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
