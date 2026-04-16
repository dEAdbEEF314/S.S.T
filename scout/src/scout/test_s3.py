import boto3
import os
import logging
from dotenv import load_dotenv
from botocore.config import Config

def test_connection():
    load_dotenv('../.env') # Path to root .env
    endpoint = os.getenv("S3_ENDPOINT_URL")
    access = os.getenv("S3_ACCESS_KEY")
    secret = os.getenv("S3_SECRET_KEY")
    
    print(f"Testing with access key: {access[:4]}...")

    # Configure boto3 to be less strict about region and use v4 signature
    s3_config = Config(
        signature_version='s3v4',
        retries={'max_attempts': 0}
    )

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="us-east-1", # Default
        config=s3_config
    )
    
    try:
        print("Trial 1: Standard ListBuckets...")
        s3.list_buckets()
        print("Trial 1 Success!")
    except Exception as e:
        print(f"Trial 1 Failed: {e}")
        
        try:
            print("Trial 2: ListBuckets without region...")
            s3_no_region = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access,
                aws_secret_access_key=secret
            )
            s3_no_region.list_buckets()
            print("Trial 2 Success!")
        except Exception as e2:
            print(f"Trial 2 Failed: {e2}")

if __name__ == "__main__":
    test_connection()
