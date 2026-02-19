"""
Tests for omniman.registry module.

Covers:
- Validator, Modifier, DirectiveHandler, IssueResolver protocols
- Registry registration and retrieval
- Type checking and duplicate registration errors
"""

from __future__ import annotations

from django.test import TestCase

from omniman import registry


class MockValidator:
    """Valid Validator implementation."""
    code = "test-validator"
    stage = "draft"

    def validate(self, *, channel, session, ctx):
        pass


class MockModifier:
    """Valid Modifier implementation."""
    code = "test-modifier"
    order = 10

    def apply(self, *, channel, session, ctx):
        pass


class MockDirectiveHandler:
    """Valid DirectiveHandler implementation."""
    topic = "test.topic"

    def handle(self, *, message, ctx):
        pass


class MockIssueResolver:
    """Valid IssueResolver implementation."""
    source = "test"

    def resolve(self, *, session, issue, action_id, ctx):
        return session


class ValidatorRegistryTests(TestCase):
    """Tests for validator registration."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_register_validator(self) -> None:
        """Should register a valid validator."""
        validator = MockValidator()
        registry.register_validator(validator)

        validators = registry.get_validators()
        self.assertEqual(len(validators), 1)
        self.assertEqual(validators[0], validator)

    def test_get_validators_by_stage(self) -> None:
        """Should filter validators by stage."""
        draft_validator = MockValidator()
        draft_validator.stage = "draft"

        commit_validator = MockValidator()
        commit_validator.code = "commit-validator"
        commit_validator.stage = "commit"

        registry.register_validator(draft_validator)
        registry.register_validator(commit_validator)

        draft_only = registry.get_validators(stage="draft")
        self.assertEqual(len(draft_only), 1)
        self.assertEqual(draft_only[0].code, "test-validator")

        commit_only = registry.get_validators(stage="commit")
        self.assertEqual(len(commit_only), 1)
        self.assertEqual(commit_only[0].code, "commit-validator")

    def test_register_invalid_validator_raises_type_error(self) -> None:
        """Should raise TypeError for non-Validator objects."""
        invalid = object()

        with self.assertRaises(TypeError) as ctx:
            registry.register_validator(invalid)

        self.assertIn("Expected Validator", str(ctx.exception))


class ModifierRegistryTests(TestCase):
    """Tests for modifier registration."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_register_modifier(self) -> None:
        """Should register a valid modifier."""
        modifier = MockModifier()
        registry.register_modifier(modifier)

        modifiers = registry.get_modifiers()
        self.assertEqual(len(modifiers), 1)
        self.assertEqual(modifiers[0], modifier)

    def test_get_modifiers_sorted_by_order(self) -> None:
        """Should return modifiers sorted by order."""
        mod1 = MockModifier()
        mod1.code = "mod1"
        mod1.order = 30

        mod2 = MockModifier()
        mod2.code = "mod2"
        mod2.order = 10

        mod3 = MockModifier()
        mod3.code = "mod3"
        mod3.order = 20

        registry.register_modifier(mod1)
        registry.register_modifier(mod2)
        registry.register_modifier(mod3)

        modifiers = registry.get_modifiers()
        codes = [m.code for m in modifiers]
        self.assertEqual(codes, ["mod2", "mod3", "mod1"])

    def test_register_invalid_modifier_raises_type_error(self) -> None:
        """Should raise TypeError for non-Modifier objects."""
        invalid = {"code": "fake", "order": 1}

        with self.assertRaises(TypeError) as ctx:
            registry.register_modifier(invalid)

        self.assertIn("Expected Modifier", str(ctx.exception))


class DirectiveHandlerRegistryTests(TestCase):
    """Tests for directive handler registration."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_register_directive_handler(self) -> None:
        """Should register a valid handler."""
        handler = MockDirectiveHandler()
        registry.register_directive_handler(handler)

        retrieved = registry.get_directive_handler("test.topic")
        self.assertEqual(retrieved, handler)

    def test_get_all_directive_handlers(self) -> None:
        """Should return all handlers."""
        h1 = MockDirectiveHandler()
        h1.topic = "topic.one"

        h2 = MockDirectiveHandler()
        h2.topic = "topic.two"

        registry.register_directive_handler(h1)
        registry.register_directive_handler(h2)

        handlers = registry.get_directive_handlers()
        self.assertEqual(len(handlers), 2)
        self.assertIn("topic.one", handlers)
        self.assertIn("topic.two", handlers)

    def test_register_duplicate_topic_raises_value_error(self) -> None:
        """Should raise ValueError when registering duplicate topic."""
        handler1 = MockDirectiveHandler()
        handler2 = MockDirectiveHandler()

        registry.register_directive_handler(handler1)

        with self.assertRaises(ValueError) as ctx:
            registry.register_directive_handler(handler2)

        self.assertIn("already registered", str(ctx.exception))
        self.assertIn("test.topic", str(ctx.exception))

    def test_register_invalid_handler_raises_type_error(self) -> None:
        """Should raise TypeError for non-DirectiveHandler objects."""
        invalid = lambda: None  # noqa

        with self.assertRaises(TypeError) as ctx:
            registry.register_directive_handler(invalid)

        self.assertIn("Expected DirectiveHandler", str(ctx.exception))

    def test_get_nonexistent_handler_returns_none(self) -> None:
        """Should return None for unknown topic."""
        result = registry.get_directive_handler("unknown.topic")
        self.assertIsNone(result)


class IssueResolverRegistryTests(TestCase):
    """Tests for issue resolver registration."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_register_issue_resolver(self) -> None:
        """Should register a valid resolver."""
        resolver = MockIssueResolver()
        registry.register_issue_resolver(resolver)

        retrieved = registry.get_issue_resolver("test")
        self.assertEqual(retrieved, resolver)

    def test_get_all_issue_resolvers(self) -> None:
        """Should return all resolvers."""
        r1 = MockIssueResolver()
        r1.source = "stock"

        r2 = MockIssueResolver()
        r2.source = "payment"

        registry.register_issue_resolver(r1)
        registry.register_issue_resolver(r2)

        resolvers = registry.get_issue_resolvers()
        self.assertEqual(len(resolvers), 2)
        self.assertIn("stock", resolvers)
        self.assertIn("payment", resolvers)

    def test_register_duplicate_source_raises_value_error(self) -> None:
        """Should raise ValueError when registering duplicate source."""
        resolver1 = MockIssueResolver()
        resolver2 = MockIssueResolver()

        registry.register_issue_resolver(resolver1)

        with self.assertRaises(ValueError) as ctx:
            registry.register_issue_resolver(resolver2)

        self.assertIn("already registered", str(ctx.exception))
        self.assertIn("test", str(ctx.exception))

    def test_register_invalid_resolver_raises_type_error(self) -> None:
        """Should raise TypeError for non-IssueResolver objects."""
        invalid = "not a resolver"

        with self.assertRaises(TypeError) as ctx:
            registry.register_issue_resolver(invalid)

        self.assertIn("Expected IssueResolver", str(ctx.exception))

    def test_get_nonexistent_resolver_returns_none(self) -> None:
        """Should return None for unknown source."""
        result = registry.get_issue_resolver("unknown")
        self.assertIsNone(result)


class RegistryClearTests(TestCase):
    """Tests for registry.clear()."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_clear_removes_all_registrations(self) -> None:
        """Should clear all registered items."""
        registry.register_validator(MockValidator())
        registry.register_modifier(MockModifier())

        handler = MockDirectiveHandler()
        handler.topic = "clear.test"
        registry.register_directive_handler(handler)

        resolver = MockIssueResolver()
        resolver.source = "clear"
        registry.register_issue_resolver(resolver)

        # Verify registered
        self.assertEqual(len(registry.get_validators()), 1)
        self.assertEqual(len(registry.get_modifiers()), 1)
        self.assertEqual(len(registry.get_directive_handlers()), 1)
        self.assertEqual(len(registry.get_issue_resolvers()), 1)

        # Clear
        registry.clear()

        # Verify cleared
        self.assertEqual(len(registry.get_validators()), 0)
        self.assertEqual(len(registry.get_modifiers()), 0)
        self.assertEqual(len(registry.get_directive_handlers()), 0)
        self.assertEqual(len(registry.get_issue_resolvers()), 0)
