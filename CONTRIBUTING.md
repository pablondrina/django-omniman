# Contributing to Django Omniman

Thank you for your interest in contributing to Django Omniman!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/your-org/omniman.git
cd omniman
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

4. Run tests:
```bash
pytest
```

## Code Style

We use the following tools for code quality:

- **Black** for code formatting
- **Ruff** for linting
- **mypy** for type checking

Run all checks:
```bash
black omniman/
ruff check omniman/
mypy omniman/
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation if needed
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to your fork (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## Commit Messages

Follow the conventional commits specification:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `style:` formatting, missing semicolons, etc.
- `refactor:` code refactoring
- `test:` adding or updating tests
- `chore:` maintenance tasks

## Testing

- Write tests for all new functionality
- Maintain test coverage above 80%
- Use pytest fixtures for common test setup

## Documentation

- Update docstrings for public APIs
- Update README.md for user-facing changes
- Update CHANGELOG.md for all changes

## Questions?

Feel free to open an issue for any questions or discussions.
