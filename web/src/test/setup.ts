import "@testing-library/jest-dom";
import { beforeEach } from "vitest";

if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}

beforeEach(() => {
  if (typeof window !== "undefined") {
    window.location.hash = "";
  }
});

