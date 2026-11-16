"""Vercel entry point: Vercel runs this file as the serverless function and sends every request to it."""
from app.main import app  # noqa: F401
