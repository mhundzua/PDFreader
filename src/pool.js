/**
 * Runs `worker` over `items` with at most `concurrency` in flight at once.
 * Calls onEach(result, index) as each item finishes (in whatever order they complete).
 */
async function runWithConcurrency(items, concurrency, worker, onEach) {
  let nextIndex = 0;

  async function runOne() {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      const result = await worker(items[index], index);
      if (onEach) await onEach(result, index);
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, items.length) }, runOne);
  await Promise.all(workers);
}

module.exports = { runWithConcurrency };
