# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Stack

Desktop application built with Tauri 2, React, and TypeScript for Windows, Linux, and macOS. Rust owns desktop integration, settings, job lifecycle, and the worker protocol. The existing Python download and PDF-organization engine remains bundled over versioned JSON-lines. This is a desktop-first Operate surface.

## Users

Trains.com subscribers who want to download magazine issues and Model Railroader track-plan PDFs into a reliable local archive, organize existing PDFs, and find or download missing magazine issues.

## Product Purpose

The application downloads Trains.com magazine issues and PDFs from the Model Railroader Track Plan Database, then helps users organize and maintain those files locally. Success means users can build and keep a reliable archive without silently missing issues or losing existing PDFs.

## Positioning

A cross-platform desktop utility that brings authenticated magazine downloads, track-plan downloads, PDF organization, and missing-issue follow-up into one workflow.

## Operating Context

- Runs as a desktop application on Windows, Linux, and macOS. Tauri renders the React interface in the platform webview; the Python worker remains responsible for download, authentication, and PDF-organization behavior. Google Chrome is required; the matching ChromeDriver is downloaded automatically. Windows portable builds require WebView2; the per-user installer provides its bootstrapper.
- Magazine downloads require an active Trains.com subscription and access to the requested issue. On first use, the user signs in through a visible Chrome window. The app reuses saved session cookies for the magazine and track-plan workflows.
- Users choose local magazine and track-plan folders. Settings and resumable-download state persist between sessions.
- The built-in organizer can process an existing folder of PDFs independently of downloading.

## Capabilities and Constraints

- Currently supports Model Railroader, Trains Magazine, Classic Toy Trains, Classic Trains, and Garden Railways.
- Downloads recent issues from direct PDF links and older flipbook issues through the browser. Some older digitized-only issues, read-only pages, and membership-gated issues are unavailable; the app reports these without counting them as successful downloads.
- Scans the paginated Model Railroader Track Plan Database, saves plan PDFs under their original filenames, and skips plans already present in the selected folder.
- Resumes magazine downloads across runs and can download missing issues after organizing a single-magazine collection.
- Organizes PDFs into year folders with consistent names and metadata. It validates PDF integrity, leaves corrupt inputs in place, reports destination conflicts, and summarizes missing issues using known publication schedules.
- An interrupted or blocked archive scan is a failure, not an empty or complete archive. Issues found before the failure are retained and reported.
- The app is intended for personal use. Users must follow Trains.com terms and only access content available to their subscription.
- Credentials are not stored. Session-cookie files contain authenticated data and must remain private.

## Brand Commitments

- Product name: Trains.com Magazine & Track Plan Downloader.

## Evidence on Hand

- The current README, application source, tests, and a committed first-launch screenshot document the existing product and workflows.
- No customer testimonials, external usage metrics, or third-party product claims are supplied. Future work must not invent them.

## Product Principles

- Optimize for a reliable local archive from discovery through organization.
- Report incomplete discovery honestly and preserve issues already found.
- Protect users' local collections by skipping existing files, retaining corrupt inputs, and surfacing conflicts.
- Keep account access limited to reusable session cookies; never store or expose passwords or cookie values.
