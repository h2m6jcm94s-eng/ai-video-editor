import { describe, expect, it } from "vitest";
import { buildMaskSourceMap, collectMaskAssetIds } from "./renders";

describe("collectMaskAssetIds", () => {
  it("collects the first mask asset id for each source asset", () => {
    const rows = [
      {
        id: "clip-1",
        storageKey: "key-clip-1",
        metadata: { segmentation: { maskAssetIds: ["mask-1", "mask-2"] } },
      },
      {
        id: "clip-2",
        storageKey: "key-clip-2",
        metadata: { segmentation: { maskAssetIds: ["mask-3"] } },
      },
      { id: "song-1", storageKey: "key-song", metadata: {} },
    ];

    const result = collectMaskAssetIds(rows);

    expect(result.maskAssetIdMap).toEqual({
      "clip-1": "mask-1",
      "clip-2": "mask-3",
    });
    expect(result.maskAssetIds).toEqual(["mask-1", "mask-2", "mask-3"]);
  });

  it("returns empty maps when no segmentation metadata exists", () => {
    const result = collectMaskAssetIds([{ id: "clip-1", storageKey: "key-1", metadata: {} }]);
    expect(result.maskAssetIdMap).toEqual({});
    expect(result.maskAssetIds).toEqual([]);
  });
});

describe("buildMaskSourceMap", () => {
  it("maps source asset ids to mask storage keys", () => {
    const maskAssetIdMap = {
      "clip-1": "mask-1",
      "clip-2": "mask-3",
    };
    const maskRows = [
      { id: "mask-1", storageKey: "r2://masks/mask-1.png" },
      { id: "mask-3", storageKey: "r2://masks/mask-3.png" },
    ];

    const result = buildMaskSourceMap(maskAssetIdMap, maskRows);

    expect(result).toEqual({
      "clip-1": "r2://masks/mask-1.png",
      "clip-2": "r2://masks/mask-3.png",
    });
  });

  it("omits source assets whose mask asset is missing a storage key", () => {
    const result = buildMaskSourceMap({ "clip-1": "mask-missing" }, []);
    expect(result).toEqual({});
  });
});
