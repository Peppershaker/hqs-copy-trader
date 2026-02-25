/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  // Tell Turbopack which workspace root to use so Next won't infer it
  // (prevents warning when there are multiple lockfiles)
  turbopack: {
    root: ".",
  },
  // Static export produces files in out/
  // No image optimization in static mode
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
