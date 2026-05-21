export async function GET() {
  return Response.json({
    status: "ok",
    service: "sentinel-web",
    version: "0.1.0",
  });
}
