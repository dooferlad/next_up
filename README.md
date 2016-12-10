# Next Up
This service exists in two parts - a web server written in Go and a scraper
written in Python. This is mostly because it is much easier to debug Python
scraping web services and json handling in Python is much easier. The scraper
inserts information into a MongoDB and the server serves up an AngularJS site
that displays them.

## Why not all Python?
Fun. I am learning Go. It has good socket.io support (which I intend to use)
and lives in a world where parallelism is assumed, which is nice for web
services.

## Why not all Go?
Defining types for all the JSON documents I wanted to load is dull, especially
when I am not using all of them. Using interfaces and type assertions is also
dull.

## No tests? Commented out code? Is all your code like this?
No. This is an evolving hack to improve my day and, litterally, works for me.
It isn't good code, but that doesn't meen I shouldn't share it.
