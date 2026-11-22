import { NextRequest } from "next/server";
import { privateJson, viewer } from "../../../lib/server/auth";
import { deviceIdentity, digest } from "../../../lib/server/security";
import { rest } from "../../../lib/server/store";

export async function GET(req: NextRequest) {
  try {
    const owner = await viewer();
    const device = deviceIdentity(req.cookies.get("vc_device")?.value);
    const usage = await rest("rpc/device_usage", { p_device: digest("quota", device.id) });
    const response = privateJson({
      owner,
      usage,
      limits: owner ? { quick: 30, deep: 10 } : { quick: 10, deep: 3 },
    });
    response.cookies.set("vc_device", device.cookie, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: req.nextUrl.protocol === "https:",
      maxAge: 86400 * 365,
    });
    return response;
  } catch {
    return privateJson({}, 503);
  }
}
