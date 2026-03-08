# Contributing to Momahub

Thank you for your interest in contributing to Momahub! As a distributed AI inference network, we value contributions that improve performance, resilience, security, and usability.

## Getting Started

1. **Fork the Repository**: Create a personal fork on GitHub.
2. **Clone Locally**:
   ```bash
   git clone https://github.com/digital-duck/momahub.py.git
   cd momahub.py
   ```
3. **Set Up Development Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -e ".[dev]"
   ```

## Development Workflow

### Branching
- Create a feature branch for your changes: `git checkout -b feature/your-feature-name` or `bugfix/your-fix-name`.

### Coding Standards
- **Python Version**: We target Python 3.11+.
- **Type Hints**: Use Pydantic models for schema and type hints for function signatures.
- **Async/Await**: The core hub and agent logic is asynchronous; maintain this pattern for I/O bound tasks.
- **Formatting**: We follow standard PEP 8 conventions.

### Testing
Before submitting a pull request, ensure all tests pass:
```bash
pytest tests/unit/ -v
```
If you add a new feature, please include corresponding unit tests in `tests/unit/`.

## Submitting Changes

1. **Commit**: Write clear, concise commit messages.
2. **Push**: Push your branch to your fork.
3. **Pull Request**: Open a PR against the `main` branch of the original repository.
4. **Review**: Maintainers will review your PR and may suggest changes.

## Research & SPL
Momahub is closely tied to the **Structured Prompt Language (SPL)**. If your changes affect the SPL adapter or compiler pipeline, please refer to the foundational paper:
- [SPL: Structured Prompt Language for Generative AI (arXiv:2602.21257)](https://arxiv.org/abs/2602.21257)

## License
By contributing to Momahub, you agree that your contributions will be licensed under the **Apache 2.0 License**.
