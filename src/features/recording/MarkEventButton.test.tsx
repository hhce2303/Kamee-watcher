import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import MarkEventButton from "./MarkEventButton";

describe("MarkEventButton", () => {
  it("has an accessible name distinct from the decorative bullet", () => {
    render(<MarkEventButton onClick={() => {}} />);
    expect(screen.getByRole("button", { name: "Marcar evento" })).toBeInTheDocument();
  });

  it("calls onClick when enabled", async () => {
    const onClick = vi.fn();
    render(<MarkEventButton onClick={onClick} />);

    await userEvent.click(screen.getByRole("button", { name: "Marcar evento" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled and does not fire onClick when disabled", async () => {
    const onClick = vi.fn();
    render(<MarkEventButton onClick={onClick} disabled />);

    const button = screen.getByRole("button", { name: "Marcar evento" });
    expect(button).toBeDisabled();

    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
