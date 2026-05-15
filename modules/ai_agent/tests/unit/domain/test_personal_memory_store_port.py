from __future__ import annotations

import pytest
from uuid import uuid4

from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


class TestPersonalMemoryStoreIsAbstract:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PersonalMemoryStore()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        class Incomplete(PersonalMemoryStore):
            pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass_instantiates(self):
        class Complete(PersonalMemoryStore):
            async def load_index(self, user_id):
                return []
            async def save_index(self, user_id, refs):
                pass
            async def load_file(self, user_id, filename):
                raise FileNotFoundError
            async def save_file(self, user_id, file):
                pass
            async def delete_file(self, user_id, filename):
                pass
            async def load_embedding(self, user_id, name):
                return None
            async def save_embedding(self, user_id, name, embedding):
                pass

        store = Complete()
        assert store is not None
