import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game_service import GameRoom, ProductionGame, GameService, load_catalog


class FakeDB:
    def __init__(self):
        self.balances = {"1": 100, "2": 100}
        self.paid = []
        self.refunds = []
        self.calls = []

    async def reserve_bet_by_telegram_id(self, uid, amount, reference, description):
        if self.balances.get(uid, 0) < amount:
            return False
        self.balances[uid] -= amount
        self.calls.append(("bet", uid, reference))
        return True

    async def refund_bet_by_telegram_id(self, uid, amount, reference, description):
        self.balances[uid] += amount
        self.refunds.append((uid, amount, reference))
        return True

    async def add_player_to_game_by_telegram_id(self, *args):
        return None

    async def update_game_financials(self, *args):
        return None

    async def update_game_status(self, *args):
        return None

    async def update_game_called_numbers(self, *args):
        return None

    async def update_player_marks(self, *args):
        return None

    async def update_game_finished(self, *args, **kwargs):
        self.calls.append(("finish", args, kwargs))

    async def pay_winner_once_by_telegram_id(self, uid, amount, reference, description):
        self.balances[uid] += amount
        self.paid.append((uid, amount, reference))
        return True

    async def mark_payout_paid(self, game_id, uid):
        return None


def test_catalog_has_400_valid_cards():
    cards = load_catalog()
    assert len(cards) == 400
    for card in cards.values():
        assert len(card) == 25
        assert len(set(card)) == 25
        for col in range(5):
            values = [card[row * 5 + col] for row in range(5)]
            assert all(col * 15 + 1 <= n <= col * 15 + 15 for n in values)


def test_line_bingo_and_single_settlement():
    async def run():
        db = FakeDB()
        room = GameRoom("classic", "Classic", 10, 80, 2, 400, 2, 0, "line")
        game = ProductionGame("g1", room, db)
        assert (await game.add_player("1", "A", 1))[0]
        assert (await game.add_player("2", "B", 2))[0]
        await game.start()

        # Force the next five calls to be the first row of both cards.
        p1, p2 = game.players["1"], game.players["2"]
        target = list(dict.fromkeys([p1.card[i] for i in range(5)] + [p2.card[i] for i in range(5)]))
        game._number_order = target + [n for n in range(1, 76) if n not in target]
        game._next_number_index = 0

        for _ in range(len(target)):
            await game.call_next_number()
            if game.status == "finished":
                break

        # If both cards complete a line on the same called number, both are settled together.
        expected = [uid for uid, p in game.players.items() if game.has_bingo_from_called_numbers(p)]
        assert game.status == "finished"
        assert set(game.winners) == set(expected)
        assert len(db.paid) == len(game.winners)
        assert sum(amount for _, amount, _ in db.paid) == 16

        # A second settlement attempt cannot happen through the game object.
        before = len(db.paid)
        await game._finish_locked(game.winners)
        assert len(db.paid) == before

    asyncio.run(run())

