import { afterEach, expect, test, vi } from "vitest";
import { submitJob, getJob, getCv } from "./api";

afterEach(() => vi.restoreAllMocks());

test("submitJob posts both files and returns the job id", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    json: async () => ({ job_id: "abc" }),
  });
  vi.stubGlobal("fetch", fetchMock);

  const id = await submitJob(new File(["cv"], "cv.txt"), new File(["jd"], "jd.txt"));

  expect(id).toBe("abc");
  const [url, opts] = fetchMock.mock.calls[0];
  expect(url).toBe("/jobs");
  expect(opts.method).toBe("POST");
  expect(opts.body).toBeInstanceOf(FormData);
});

test("getJob returns the parsed status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ status: "running", error: null }),
    }),
  );
  expect(await getJob("abc")).toEqual({ status: "running", error: null });
});

test("getCv returns the body text", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ text: async () => "MY CV" }));
  expect(await getCv("abc")).toBe("MY CV");
});
