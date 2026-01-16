# MedAgent for German, medical guidelines (simplified)

> **Goal:** a framework for configurable RAG-workflows based on knowledge base consisting of German, medical guidelines (typically from AWMF)

This is a simplified version of the original full framework with the following components:
1. The backend allowing to setup and interact with RAG systems (based on individual components) and setup a knowledge base, ...
2. The frontend allowing to interact with created systems, and to chunk guidelines to setup a knowledge base.
3. An authentication service to only allow access for authorized users (with username and password).

All provided in docker containers for easy deployment.
