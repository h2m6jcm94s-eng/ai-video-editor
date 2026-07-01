import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";
import { sendCutlistApprovedSignal } from "../services/temporal";

vi.mock("../services/temporal", () => ({
  sendCutlistApprovedSignal: vi.fn(),
}));

describe("Project cut-list edit attribution", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const PROJ_ID = "8562dc1a-1493-42ee-ab6e-1075b83c88d6";
  const RENDER_ID = "fc6b55b4-01cd-431b-808a-35b4f28613e1";

  const mockProject = {
    id: PROJ_ID,
    userId: "test-user-id",
    name: "Test",
    status: "uploading",
    referenceAssetId: "ref-1",
    songAssetId: "song-1",
    clipAssetIds: [],
    styleTier: "full_remix",
    mode: "auto",
    cutList: {
      globals: {
        totalDurationS: 20,
        tempoBpm: 120,
        timeSignature: "4/4",
        aspectRatio: "9:16",
      },
      slots: [
        {
          index: 0,
          startS: 0,
          durationS: 5,
          beatIndex: 0,
          section: "intro",
          targetShotType: "wide",
          subjectHint: "person",
          motionHint: "static",
          transitionIn: "hard_cut",
          transitionOut: "hard_cut",
        },
      ],
    },
  };

  const newCutList = {
    globals: {
      totalDurationS: 20,
      tempoBpm: 120,
      timeSignature: "4/4",
      aspectRatio: "9:16",
    },
    slots: [
      {
        index: 0,
        startS: 0,
        durationS: 2.5,
        beatIndex: 0,
        section: "intro",
        targetShotType: "wide",
        subjectHint: "person",
        motionHint: "static",
        transitionIn: "hard_cut",
        transitionOut: "dissolve",
      },
      {
        index: 1,
        startS: 2.5,
        durationS: 2.5,
        beatIndex: 1,
        section: "intro",
        targetShotType: "close_up",
        subjectHint: "person",
        motionHint: "static",
        transitionIn: "dissolve",
        transitionOut: "hard_cut",
      },
    ],
  };

  it("PATCH /api/projects/:id/cutlist records attributed behavior deltas", async () => {
    vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject as any);
    vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce({
      id: RENDER_ID,
      projectId: PROJ_ID,
      status: "running",
      workflowId: "wf-123",
    } as any);
    vi.mocked(db.update).mockReturnValue({
      set: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          returning: vi.fn().mockResolvedValueOnce([{ ...mockProject, cutList: newCutList }]),
        }),
      }),
    } as any);
    vi.mocked(db.insert).mockReturnValue({
      values: vi.fn().mockReturnValue({
        returning: vi.fn().mockResolvedValue([]),
      }),
    } as any);

    const app = await buildApp();
    const res = await app.inject({
      method: "PATCH",
      url: `/api/projects/${PROJ_ID}/cutlist`,
      payload: { cutList: newCutList },
    });

    expect(res.statusCode).toBe(200);
    expect(sendCutlistApprovedSignal).toHaveBeenCalled();

    expect(vi.mocked(db.insert)).toHaveBeenCalled();
  });
});
