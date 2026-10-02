import { describe, expect, it } from "vitest";

import { withDispositionCodeOptions, workflowFilterAttributes } from "@/lib/filterAttributes";
import { decodeFiltersFromURL, resolveFilterAttributes, validateFilter } from "@/lib/filters";
import type { ActiveFilter, FilterAttribute, MultiSelectValue } from "@/types/filters";

const dispositionAttribute = workflowFilterAttributes.find(
  attribute => attribute.id === "dispositionCode"
);

if (!dispositionAttribute) {
  throw new Error("Disposition filter attribute is missing");
}

describe("disposition filters", () => {
  it("resolves URL-loaded filters against the latest catalog options", () => {
    const activeFilter: ActiveFilter = {
      attribute: dispositionAttribute,
      value: { codes: ["user_hangup"] },
      isValid: true,
    };
    const currentAttributes = withDispositionCodeOptions(
      workflowFilterAttributes,
      ["user_hangup", "call_transferred"]
    );
    const currentAttribute = currentAttributes.find(
      attribute => attribute.id === "dispositionCode"
    );
    if (!currentAttribute) {
      throw new Error("Disposition filter attribute is missing");
    }

    const [resolvedFilter] = resolveFilterAttributes(
      [activeFilter],
      currentAttributes
    );

    expect(resolvedFilter.attribute).toBe(currentAttribute);
    expect(resolvedFilter.attribute.config.options).toEqual([
      "user_hangup",
      "call_transferred",
    ]);
  });

  it("allows selecting the complete backend catalog", () => {
    const codes = Array.from({ length: 20 }, (_, index) => `code-${index}`);
    const filter: ActiveFilter = {
      attribute: {
        ...dispositionAttribute,
        config: {
          ...dispositionAttribute.config,
          options: codes,
        },
      },
      value: { codes } satisfies MultiSelectValue,
      isValid: false,
    };

    expect(validateFilter(filter)).toBeNull();
  });
});

describe("?channel= shorthand", () => {
  const channelAttribute = {
    id: "callChannel",
    label: "Type",
    type: "radio",
    config: {},
  } as unknown as FilterAttribute;
  const decode = (query: string) => decodeFiltersFromURL(new URLSearchParams(query), [channelAttribute]);

  it("turns a readable channel into the same filter the long form produces", () => {
    const [filter] = decode("channel=chat");
    expect(filter.attribute.id).toBe("callChannel");
    expect(filter.value).toEqual({ status: "chat" });
    expect(filter.isValid).toBe(true);
  });

  it.each(["telephony", "web", "chat"])("accepts %s", (channel) => {
    expect(decode(`channel=${channel}`)).toHaveLength(1);
  });

  it("ignores a value that is not a channel, rather than inventing a filter", () => {
    expect(decode("channel=all")).toEqual([]);
    expect(decode("channel=voice")).toEqual([]);
    expect(decode("")).toEqual([]);
  });

  it("an explicit filters param wins, so links shared before this existed still work", () => {
    const filters = JSON.stringify([{ id: "callChannel", value: { status: "web" } }]);
    const result = decode(`channel=chat&filters=${encodeURIComponent(filters)}`);
    expect(result).toHaveLength(1);
    expect(result[0].value).toEqual({ status: "web" });
  });

  it("does nothing when the page has no such filter to seed", () => {
    expect(decodeFiltersFromURL(new URLSearchParams("channel=chat"), [])).toEqual([]);
  });
});
