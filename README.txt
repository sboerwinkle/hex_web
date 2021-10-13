I am not taking as long as usual to write this readme, because it is late and I am tired.

This is a couple small games I wrote, as well as a small framework I wrote to write them.

This project runs on python3. In a Linux environment you should just be able to do:
$ ./launch.py
to get the server started. I think the only python module dependency is websockets (= 8.1),
but don't quote me on that.

The most important thing is that this project *does not include a webserver*.
If you don't have one, apache2 is very painless to install on most Linuxes.
Once you have one, just symlink the `html` directory here into some place in your webroot so people can access it.
The `main.html` page holds "the game".

The websockets are configured to use port 15000,
so make sure people can use that port to talk to your computer (port forwarding etc.),
and make sure nothing else is using that port (though I don't expect anything is).

I put a small but measurable amount of effort into helping new people figure out how to use it
once they're connected, and as mentioned it is late and I am tired, so I won't recap all that here.
However, I will say you can get started with "/help" once you get in.
