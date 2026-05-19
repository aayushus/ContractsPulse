# Contributing to ContractsPulse

Thank you for your interest in contributing to **ContractsPulse**! We welcome bug fixes, documentation improvements, and new feature suggestions.

## Code of Conduct

Please be respectful and constructive in all community interactions, including issues, pull requests, and discussions.

## Getting Started

1. **Fork the Repository**: Create a personal copy of the repository on GitHub.
2. **Set Up the Environment**: Follow the detailed setup instructions in the [README.md](../README.md) to launch the Docker containers or set up a manual local development environment.
3. **Create a Branch**: Create a feature branch for your changes:
   ```bash
   git checkout -b feature/my-amazing-improvement
   ```

## Development Standards

*   **FastAPI Backend**: Ensure all new endpoints are typed and document inputs/outputs with Pydantic schemas. Write clean docstrings.
*   **SvelteKit Frontend**: Keep components focused, reactive (using Svelte 5 Runes), and aligned with the monochromatic, premium dark UI aesthetic.
*   **CLI Client**: Test script arguments using the Typer helper commands.

## Submitting a Pull Request

1. Ensure all code compiles, and you've verified your changes locally.
2. Format your commit messages clearly (e.g. `feat: add Google OAuth support` or `fix: resolve JWT token expiration refresh`).
3. Open a Pull Request from your fork to our `main` branch. Provide a comprehensive summary of the changes and any testing screenshots.
