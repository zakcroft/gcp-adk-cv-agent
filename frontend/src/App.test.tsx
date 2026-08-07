import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import * as api from "./api";

afterEach(() => vi.restoreAllMocks());

async function uploadBoth() {
  await userEvent.upload(
    screen.getByLabelText(/your cv/i),
    new File(["cv"], "cv.txt", { type: "text/plain" }),
  );
  await userEvent.upload(
    screen.getByLabelText(/job description/i),
    new File(["jd"], "jd.txt", { type: "text/plain" }),
  );
}

test("shows the improved CV when the job is done", async () => {
  vi.spyOn(api, "submitJob").mockResolvedValue("job1");
  vi.spyOn(api, "getJob").mockResolvedValue({ status: "done", error: null });
  vi.spyOn(api, "getCv").mockResolvedValue("IMPROVED CV TEXT");

  render(<App pollMs={5} />);
  await uploadBoth();
  await userEvent.click(screen.getByRole("button", { name: /improve my cv/i }));

  expect(await screen.findByText("IMPROVED CV TEXT")).toBeInTheDocument();
});

test("shows the refusal reason when the job fails", async () => {
  vi.spyOn(api, "submitJob").mockResolvedValue("job1");
  vi.spyOn(api, "getJob").mockResolvedValue({
    status: "failed",
    error: "Please upload a real CV.",
  });

  render(<App pollMs={5} />);
  await uploadBoth();
  await userEvent.click(screen.getByRole("button", { name: /improve my cv/i }));

  expect(await screen.findByText(/please upload a real cv/i)).toBeInTheDocument();
});

test("rerun warns when the draft has not been downloaded", async () => {
  vi.spyOn(api, "submitJob").mockResolvedValue("job1");
  vi.spyOn(api, "getJob").mockResolvedValue({ status: "done", error: null });
  vi.spyOn(api, "getCv").mockResolvedValue("IMPROVED CV TEXT");
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

  render(<App pollMs={5} />);
  await uploadBoth();
  await userEvent.click(screen.getByRole("button", { name: /improve my cv/i }));
  await screen.findByText("IMPROVED CV TEXT");
  await userEvent.click(screen.getByRole("button", { name: /rerun/i }));

  expect(confirm).toHaveBeenCalled();
  // confirm returned false -> draft still shown
  expect(screen.getByText("IMPROVED CV TEXT")).toBeInTheDocument();
});
