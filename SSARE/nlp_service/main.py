from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from core.models import ArticleBase
import json
import logging
from core.utils import load_config
from redis import Redis
import asyncio
from prefect import task, flow
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()['nlp']
app = FastAPI()
token = config['HUGGINGFACE_TOKEN']
model = SentenceTransformer("jinaai/jina-embeddings-v2-base-en", use_auth_token=token)

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200


@task
def retrieve_articles_from_redis(redis_conn_raw, batch_size=200):
    raw_articles_json = []
    batch = redis_conn_raw.lrange('articles_without_embedding_queue', 0, batch_size - 1)
    raw_articles_json.extend(batch)
    redis_conn_raw.ltrim('articles_without_embedding_queue', batch_size, -1)
    return raw_articles_json

@task
def process_article(raw_article_json):
    raw_article = json.loads(raw_article_json)
    article = ArticleBase(**raw_article)
    embeddings = model.encode(article.headline + " ".join(article.paragraphs[:500])).tolist()
    article_with_embeddings = {
        "headline": article.headline,
        "paragraphs": article.paragraphs,
        "embeddings": embeddings,
        "embeddings_created": 1,
        "url": article.url,
        "source": article.source,
        "stored_in_qdrant": 0
    }
    logger.info(f"Generated embeddings for article: {article.url}, Embeddings Length: {len(embeddings)}")
    return article_with_embeddings

@task
def write_articles_to_redis(redis_conn_processed, articles_with_embeddings):
    serialized_articles = [json.dumps(article) for article in articles_with_embeddings]
    if serialized_articles:  # Check if the list is not empty
        redis_conn_processed.lpush('articles_with_embeddings', *serialized_articles)
        logger.info(f"Wrote {len(articles_with_embeddings)} articles with embeddings to Redis")
    else:
        logger.info("No articles to write to Redis")
        
@flow
def generate_embeddings_flow(batch_size: int):
    logger.info("Starting embeddings generation process")
    redis_conn_raw = Redis(host='redis', port=6379, db=5, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=6, decode_responses=True)

    try:
        raw_articles_json = retrieve_articles_from_redis(redis_conn_raw, batch_size)
        articles_with_embeddings = [process_article(raw_article_json) for raw_article_json in raw_articles_json]
        write_articles_to_redis(redis_conn_processed, articles_with_embeddings)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()
        time.sleep(1)  # Ensure all connections are closed properly

    logger.info("Embeddings generation process completed")

    
@app.post("/generate_embeddings")
def generate_embeddings(batch_size: int = 1000):
    logger.debug("GENERATING EMBEDDINGS")
    generate_embeddings_flow(batch_size)
    return {"message": "Embeddings generated successfully"}

@app.get("/generate_query_embeddings")
def generate_query_embedding(query: str):
    try:
        embeddings = model.encode(query).tolist()
        logger.info(f"Generated embeddings for query: {query}, Embedding Length: {len(embeddings)}")
        return {"message": "Embeddings generated", "embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))