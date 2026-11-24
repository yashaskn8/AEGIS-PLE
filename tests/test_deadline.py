import asyncio
import unittest

from aegis.protocol import Session, WireError, encode
from tests.test_protocol import Peer, opening


class Deadline(unittest.IsolatedAsyncioTestCase):
    async def test_late_receive_poisoned(self):
        class LatePeer(Peer):
            async def recv(self):
                if not self.frames.empty():
                    return await super().recv()
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return encode({'type':'result','id':'1','ok':True,
                                   'size':0,'content_b64':'','truncated':False})
                raise AssertionError('timeout did not fire')
        peer = LatePeer([opening()])
        session = Session(peer, io_timeout=0.01)
        await session.start()
        with self.assertRaises(WireError):
            await session.read('input')
        self.assertTrue(session.poisoned)
        with self.assertRaises(WireError):
            await session.finish('not accepted')

    async def test_late_send_poisoned(self):
        class LatePeer(Peer):
            async def send(self, raw):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    await super().send(raw)
        peer = LatePeer([opening(), {'type':'result','id':'1','ok':True,
                                    'size':0,'content_b64':'','truncated':False}])
        session = Session(peer, io_timeout=0.01)
        await session.start()
        with self.assertRaises(WireError):
            await session.read('input')
        self.assertTrue(session.poisoned)
        self.assertEqual(peer.frames.qsize(), 1)

    async def test_expired_success_refused_but_error_allowed(self):
        peer = Peer([opening()])
        session = Session(peer)
        await session.start()
        session.deadline = asyncio.get_running_loop().time() - 1
        with self.assertRaises(WireError):
            await session.finish('not accepted')
        self.assertFalse(session.terminal)
        await session.finish('deadline exceeded', failed=True)
        self.assertEqual(peer.sent[-1]['type'], 'error')
