"""Unit tests for transfpro.workers.base_worker module.

Requires PyQt5 to be installed. Tests are automatically skipped if PyQt5
is not available (e.g., in headless CI environments).
"""

import unittest
import threading

try:
    from transfpro.workers.base_worker import BaseWorker
    HAS_PYQT5 = True
except ImportError:
    HAS_PYQT5 = False
    BaseWorker = object  # placeholder so class definitions don't fail


if HAS_PYQT5:

    class ConcreteWorker(BaseWorker):
        """Concrete implementation of BaseWorker for testing."""

        def __init__(self, work_fn=None):
            super().__init__()
            self._work_fn = work_fn
            self.did_work = False

        def do_work(self):
            self.did_work = True
            if self._work_fn:
                self._work_fn()


@unittest.skipUnless(HAS_PYQT5, "PyQt5 not available")
class TestBaseWorkerCancellation(unittest.TestCase):
    """Test cancellation mechanism."""

    def test_not_cancelled_initially(self):
        w = ConcreteWorker()
        self.assertFalse(w.is_cancelled)

    def test_cancel_sets_flag(self):
        w = ConcreteWorker()
        w.cancel()
        self.assertTrue(w.is_cancelled)

    def test_cancel_event_is_set(self):
        w = ConcreteWorker()
        w.cancel()
        self.assertTrue(w._cancel_event.is_set())


@unittest.skipUnless(HAS_PYQT5, "PyQt5 not available")
class TestBaseWorkerRun(unittest.TestCase):
    """Test the run method."""

    def test_do_work_called(self):
        w = ConcreteWorker()
        w.run()
        self.assertTrue(w.did_work)

    def test_custom_work_fn(self):
        results = []
        w = ConcreteWorker(work_fn=lambda: results.append(42))
        w.run()
        self.assertEqual(results, [42])

    def test_error_emitted_on_exception(self):
        errors = []

        def failing_work():
            raise ValueError("test error")

        w = ConcreteWorker(work_fn=failing_work)
        w.error.connect(lambda msg: errors.append(msg))
        w.run()
        self.assertEqual(len(errors), 1)
        self.assertIn("test error", errors[0])


@unittest.skipUnless(HAS_PYQT5, "PyQt5 not available")
class TestBaseWorkerSignals(unittest.TestCase):
    """Test signal emissions."""

    def test_finished_signal(self):
        finished = []
        w = ConcreteWorker()
        w.finished.connect(lambda: finished.append(True))
        w.run()
        self.assertEqual(len(finished), 1)

    def test_status_message_signal(self):
        messages = []
        w = ConcreteWorker()
        w.status_message.connect(lambda msg: messages.append(msg))

        def emit_status():
            w.status_message.emit("processing...")

        w2 = ConcreteWorker(work_fn=emit_status)
        w2.status_message.connect(lambda msg: messages.append(msg))
        w2.run()
        self.assertIn("processing...", messages)


if __name__ == "__main__":
    unittest.main()
