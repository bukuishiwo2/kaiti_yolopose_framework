"""Separate new local occupancy from the immutable static layer's sampling edge.
Never edits a Nav2 map, sensor message or collision threshold.
"""
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

def static_sampling_mask(path):
 # One 0.05m cell covers resampling/rotation of the existing 0.05m static layer.
 return binary_dilation(np.asarray(Image.open(path))<200,structure=np.ones((3,3)))

def local_delta(grid,origin,res,map_from_frame,center,static_mask):
 yy,xx=np.indices(grid.shape);x=origin[0]+(xx+.5)*res;y=origin[1]+(yy+.5)*res;tx,ty,yaw=map_from_frame;wx=tx+np.cos(yaw)*x-np.sin(yaw)*y;wy=ty+np.sin(yaw)*x+np.cos(yaw)*y;roi=(wx-center[0])**2+(wy-center[1])**2<1.17**2;lethal=(grid>=254)&roi;col=np.floor(wx/.05).astype(int);row=999-np.floor((wy+50)/.05).astype(int);valid=(row>=0)&(row<static_mask.shape[0])&(col>=0)&(col<static_mask.shape[1]);known=np.zeros(grid.shape,dtype=bool);known[valid]=static_mask[row[valid],col[valid]];return dict(raw=int(np.sum(lethal)),new=int(np.sum(lethal&~known)),static_explained=int(np.sum(lethal&known)))
