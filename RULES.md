# RULES.md: YT-DLP Web Downloader

## Mandatory Engineering Rules

These rules are binding for all contributors, human and AI.

### Documentation

1. **Read all six documentation files** (ePRD.md, ARCHITECTURE.md, DESIGN.md, MEMORY.md, RULES.md, TRACKER.md) before modifying the project.
2. **Inspect the existing repository** before creating or replacing files.
3. **Preserve working functionality** unless a change is required and justified.
4. **Never invent** files, routes, methods, dependencies, or test results that do not exist.
5. **Never claim a command was executed** if it was not executed.

### Download Integrity

6. **Never use fake download progress** or simulated success in production code.
7. **Use yt-dlp's Python API** rather than building shell commands from user input.
8. **Never interpolate user-supplied URLs into shell commands.**

### Security

9. **Never expose arbitrary filesystem paths** to the browser.
10. **Validate every URL and request** on the server.
11. **Restrict downloads to supported YouTube URL patterns** for the MVP.
12. **Reject local file URLs, loopback targets, private network targets, and unsupported schemes.** Validate redirects and resolved destinations where applicable to prevent SSRF.
13. **Never accept arbitrary output templates, filesystem locations, or yt-dlp options** from clients.
14. **Restrict format selections to a predefined allowlist.**
15. **Limit request sizes, concurrent jobs, playlist sizes, queue depth, and download duration.**

### Architecture

16. **Use background workers for downloads.** Do not block the main request while a media file is downloading.
17. **Use unique job identifiers and safe, server-generated filenames.**
18. **Do not expose stack traces, secrets, internal paths, or raw exception details** to users.
19. **Keep progress state and error state consistent** with actual downloader events.
20. **Persist job state** and make restart behavior explicit.
21. **Do not delete files** that are actively being downloaded or served.
22. **Prevent unauthorized access** to other users' jobs and files. For public deployment, implement authentication.

### Reliability

23. **Use bounded concurrency and explicit timeouts.**
24. **Escape HTML** and render user-controlled values safely.
25. **Keep JavaScript free of hardcoded backend assumptions** that contradict ARCHITECTURE.md.
26. **Do not introduce frameworks prohibited** by the stack specification.

### Testing & Documentation

27. **Add or update tests** whenever behavior changes.
28. **Run tests** after meaningful implementation changes.
29. **Update all documentation files** whenever relevant.
30. **If a requirement cannot be implemented,** document the blocker rather than pretending it is complete.

### Legal & Ethical

31. **Use only legitimate access to media.** Do not implement bypasses for DRM, paywalls, access controls, or private-video restrictions.
32. **Before public deployment,** document abuse prevention, authentication, rate limiting, storage quotas, and acceptable-use requirements.
